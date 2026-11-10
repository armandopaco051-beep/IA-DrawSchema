import unittest
from unittest.mock import patch
from app.config.settings import settings
from app.config.agents_models import (
    get_agent_model_name, get_agent_model, get_image_fallback_models,
    get_litellm_api_base, get_litellm_api_key,
    select_text_provider, get_agent_provider,
)
from app.providers.ai_provider import configure_ai_provider

class OllamaProviderTest(unittest.TestCase):
    def test_all_agents_share_local_model_without_cloud_fallback(self):
        with patch.object(settings, 'AI_PROVIDER', 'ollama'), patch.object(settings, 'OLLAMA_MODEL', 'qwen3-vl:4b'), patch.object(settings, 'GEMINI_API_KEY', None):
            configure_ai_provider()
            for name in ('planner', 'diagram', 'suggestion', 'validation', 'codegen'):
                self.assertEqual(get_agent_model_name(name), 'openai/qwen3-vl:4b')
            self.assertEqual(get_image_fallback_models(), [])
            model = get_agent_model('planner')
            self.assertEqual(model.base_url, settings.OLLAMA_BASE_URL.rstrip('/'))
    def test_cloud_tag_is_rejected(self):
        with patch.object(settings, 'AI_PROVIDER', 'ollama'), patch.object(settings, 'OLLAMA_MODEL', 'qwen3-vl:235b-cloud'):
            with self.assertRaises(RuntimeError):
                configure_ai_provider()
    def test_legacy_provider_remains_available(self):
        with patch.object(settings, 'AI_PROVIDER', 'litellm'):
            self.assertEqual(get_agent_model_name('planner'), settings.PLANNER_MODEL)

    def test_hybrid_text_is_local_and_images_use_gemini(self):
        with patch.object(settings, 'AI_PROVIDER', 'hybrid'), \
             patch.object(settings, 'OLLAMA_MODEL', 'qwen2.5:0.5b'), \
             patch.object(settings, 'IMAGE_MODEL', 'gemini/gemini-3.5-flash-lite'), \
             patch.object(settings, 'GEMINI_API_KEY', 'test-google-key'), \
             patch.object(settings, 'OLLAMA_API_KEY', 'ollama'), \
             patch.object(settings, 'LITELLM_API_BASE', None):
            for agent in ('planner', 'diagram', 'suggestion', 'validation', 'codegen'):
                model = get_agent_model_name(agent)
                self.assertEqual(model, 'openai/qwen2.5:0.5b')
                self.assertEqual(get_litellm_api_key(model), 'ollama')
                self.assertEqual(get_litellm_api_base(model), settings.OLLAMA_BASE_URL.rstrip('/'))
            image = get_agent_model_name('image')
            self.assertEqual(image, 'gemini/gemini-3.5-flash-lite')
            self.assertEqual(get_litellm_api_key(image), 'test-google-key')
            self.assertIsNone(get_litellm_api_base(image))
            self.assertIsNone(get_agent_model('image').base_url)

    def test_missing_gemini_key_does_not_block_hybrid_text(self):
        with patch.object(settings, 'AI_PROVIDER', 'hybrid'), \
             patch.object(settings, 'GEMINI_API_KEY', None):
            configure_ai_provider('planner')
            with self.assertRaises(RuntimeError):
                configure_ai_provider('image')

    def test_request_selection_overrides_default_but_never_image_provider(self):
        with patch.object(settings, 'AI_PROVIDER', 'litellm'), \
             patch.object(settings, 'OLLAMA_MODEL', 'qwen2.5-coder:1.5b'):
            with select_text_provider('local'):
                self.assertEqual(get_agent_model_name('planner'), 'openai/qwen2.5-coder:1.5b')
                self.assertEqual(get_agent_provider('suggestion'), 'ollama')
                self.assertEqual(get_agent_provider('validation'), 'ollama')
                self.assertEqual(get_agent_provider('image'), 'litellm')
                self.assertTrue(get_agent_model_name('image').startswith('gemini/'))
            self.assertEqual(get_agent_provider('planner'), 'litellm')


class ConcurrentProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_simultaneous_users_keep_independent_providers(self):
        import asyncio
        async def inspect(provider):
            with select_text_provider(provider):
                await asyncio.sleep(0)
                return get_agent_provider('planner'), get_agent_provider('image')
        results = await asyncio.gather(inspect('local'), inspect('gemini'))
        self.assertEqual(results, [('ollama', 'litellm'), ('litellm', 'litellm')])
