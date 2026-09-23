import json
import re
import unittest

from app.services.spring_boot_builder import build_spring_boot_project


class SpringBootBuilderMetadataTest(unittest.TestCase):
    def test_generates_mobile_discovery_contract(self):
        context = {
            "diagrama": {
                "contenido": {
                    "nodes": [
                        {
                            "data": {
                                "name": "Producto",
                                "attributes": [
                                    {
                                        "name": "id",
                                        "type": "BIGINT",
                                        "primaryKey": True,
                                        "nullable": False,
                                    },
                                    {
                                        "name": "nombre",
                                        "type": "VARCHAR",
                                        "nullable": False,
                                    },
                                ],
                            }
                        }
                    ]
                }
            }
        }

        files, _ = build_spring_boot_project(
            context,
            "restaurante-api",
            "com.drawschema.generated",
            "restaurante",
        )
        by_path = {generated.path: generated.content for generated in files}
        controller = by_path[
            "src/main/java/com/drawschema/generated/controllers/BackendMetadataController.java"
        ]
        properties = by_path["src/main/resources/application.properties"]

        match = re.search(r'SCHEMA_JSON = """\n(.*?)\n\s*""";', controller, re.S)
        self.assertIsNotNone(match)
        schema = json.loads(match.group(1))

        self.assertEqual(schema["proyecto"], "restaurante-api")
        self.assertEqual(schema["entidades"][0]["endpoint"], "/api/productos")
        self.assertTrue(schema["entidades"][0]["atributos"]["nombre"]["required"])
        self.assertIn("server.address=0.0.0.0", properties)
        self.assertIn("server.port=${SERVER_PORT:8086}", properties)


if __name__ == "__main__":
    unittest.main()
