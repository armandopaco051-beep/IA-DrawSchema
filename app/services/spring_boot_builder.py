from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.codegen import GeneratedFile


@dataclass
class Attribute:
    """Representa un atributo del diagrama ya convertido a datos utiles para Java."""

    name: str
    java_name: str
    java_type: str
    primary_key: bool
    nullable: bool

@dataclass
class Entity:
    """Representa una clase UML convertida en entidad candidata para Spring Boot."""

    name: str
    class_name: str
    variable_name: str
    route_name: str
    table_name: str
    attributes: list[Attribute]
    id_attribute: Attribute
    generated_id: bool
    is_composite_id: bool = False
    composite_id_class_name: str | None = None
    pk_attributes: list[Attribute] = field(default_factory=list)



def _clean_words(value: str) -> list[str]:
    """Divide un texto en palabras limpias para construir nombres de clases/campos."""

    words = re.split(r"[^a-zA-Z0-9]+", value.strip())
    return [word for word in words if word]


def to_pascal_case(value: str, fallback: str = "Entity") -> str:
    """Convierte un texto a PascalCase para nombres de clases Java."""

    words = _clean_words(value)

    if not words:
        return fallback

    result = "".join(word[:1].upper() + word[1:] for word in words)

    if result[:1].isdigit():
        result = f"{fallback}{result}"

    return result


def to_camel_case(value: str, fallback: str = "field") -> str:
    """Convierte un texto a camelCase para variables, campos y nombres de objetos."""

    pascal = to_pascal_case(value, fallback.capitalize())
    return pascal[:1].lower() + pascal[1:]


def to_snake_case(value: str) -> str:
    """Convierte un texto a snake_case para nombres de tabla en PostgreSQL."""

    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower() or "entity"


def pluralize(value: str) -> str:
    """Genera un plural simple para formar rutas REST como /api/clientes."""

    value = to_snake_case(value).replace("_", "-")

    if value.endswith("s"):
        return value

    return f"{value}s"


def map_java_type(raw_type: Any) -> str:
    """Mapea tipos del diagrama o PostgreSQL a tipos Java."""

    normalized = str(raw_type or "String").strip().upper()

    mappings = {
        "BIGINT": "Long",
        "LONG": "Long",
        "INT": "Integer",
        "INTEGER": "Integer",
        "SMALLINT": "Integer",
        "SERIAL": "Integer",
        "VARCHAR": "String",
        "CHAR": "String",
        "TEXT": "String",
        "STRING": "String",
        "DECIMAL": "BigDecimal",
        "NUMERIC": "BigDecimal",
        "DOUBLE": "Double",
        "FLOAT": "Float",
        "DATE": "LocalDate",
        "LOCALDATE": "LocalDate",
        "TIMESTAMP": "LocalDateTime",
        "DATETIME": "LocalDateTime",
        "BOOLEAN": "Boolean",
        "BOOL": "Boolean",
    }

    return mappings.get(normalized, "String")


def map_schema_type(java_type: str) -> str:
    """Convierte tipos Java a los tipos simples que entiende la app movil."""

    mappings = {
        "Long": "int",
        "Integer": "int",
        "Double": "double",
        "Float": "double",
        "BigDecimal": "double",
        "Boolean": "boolean",
        "LocalDate": "date",
        "LocalDateTime": "datetime",
    }
    return mappings.get(java_type, "string")


def parse_entities(context: dict[str, Any]) -> tuple[list[Entity], list[str]]:
    """Lee el JSONB del diagrama y lo transforma en entidades internas."""

    warnings: list[str] = []
    diagrama = context.get("diagrama") or {}
    contenido = diagrama.get("contenido") or {}
    nodes = contenido.get("nodes") or []
    entities: list[Entity] = []
    used_names: set[str] = set()

    for index, node in enumerate(nodes):
        data = node.get("data") or {}
        raw_name = str(data.get("name") or f"Entidad{index + 1}")
        class_name = to_pascal_case(raw_name, f"Entity{index + 1}")

        if class_name in used_names:
            warnings.append(f"La entidad {class_name} estaba duplicada; se renombro automaticamente.")
            class_name = f"{class_name}{index + 1}"

        used_names.add(class_name)

        attributes: list[Attribute] = []

        for attr_index, attr in enumerate(data.get("attributes") or []):
            attr_name = str(attr.get("name") or f"campo{attr_index + 1}")
            java_name = to_camel_case(attr_name, f"field{attr_index + 1}")
            java_type = map_java_type(attr.get("type"))
            primary_key = bool(attr.get("primaryKey"))
            nullable = bool(attr.get("nullable", True))

            attributes.append(
                Attribute(
                    name=attr_name,
                    java_name=java_name,
                    java_type=java_type,
                    primary_key=primary_key,
                    nullable=nullable,
                )
            )

        id_attributes = [attribute for attribute in attributes if attribute.primary_key]
        generated_id = False
        is_composite_id = False
        composite_id_class_name = None
        pk_attributes = []

        if len(id_attributes) > 1:
            is_composite_id = True
            composite_id_class_name = f"{class_name}Id"
            pk_attributes = id_attributes
            id_attribute = Attribute(
                name="id",
                java_name="id",
                java_type=composite_id_class_name,
                primary_key=True,
                nullable=False,
            )
            warnings.append(
                f"La entidad {class_name} posee clave compuesta con {len(id_attributes)} campos ({[a.name for a in id_attributes]}); "
                f"se generara la clase @Embeddable {composite_id_class_name}."
            )
        elif id_attributes:
            id_attribute = id_attributes[0]
        else:
            generated_id = True
            id_attribute = Attribute(
                name="id",
                java_name="id",
                java_type="Long",
                primary_key=True,
                nullable=False,
            )
            attributes.insert(0, id_attribute)
            warnings.append(
                f"La entidad {class_name} no tenia primaryKey; se genero id Long automaticamente."
            )

        entities.append(
            Entity(
                name=raw_name,
                class_name=class_name,
                variable_name=to_camel_case(class_name),
                route_name=pluralize(class_name),
                table_name=to_snake_case(class_name),
                attributes=attributes,
                id_attribute=id_attribute,
                generated_id=generated_id,
                is_composite_id=is_composite_id,
                composite_id_class_name=composite_id_class_name,
                pk_attributes=pk_attributes,
            )
        )


    if not entities:
        raise ValueError("No se puede generar backend porque el diagrama no tiene clases.")

    return entities, warnings


def package_path(base_package: str) -> str:
    """Convierte un paquete Java en ruta de carpetas."""

    return base_package.replace(".", "/")


def common_imports(attributes: list[Attribute]) -> list[str]:
    """Calcula imports Java adicionales segun los tipos usados por los atributos."""

    imports: set[str] = set()

    for attribute in attributes:
        if attribute.java_type == "BigDecimal":
            imports.add("java.math.BigDecimal")
        if attribute.java_type == "LocalDate":
            imports.add("java.time.LocalDate")
        if attribute.java_type == "LocalDateTime":
            imports.add("java.time.LocalDateTime")

    return sorted(imports)


def validation_annotation(attribute: Attribute) -> str | None:
    """Devuelve la anotacion de validacion que corresponde a un atributo."""

    if attribute.primary_key or attribute.nullable:
        return None

    if attribute.java_type == "String":
        return "@NotBlank"

    return "@NotNull"


def field_declaration(attribute: Attribute, include_validation: bool = True) -> list[str]:
    """Genera las lineas Java de un campo, incluyendo JPA y validaciones."""

    lines: list[str] = []
    validation = validation_annotation(attribute) if include_validation else None

    if validation:
        lines.append(f"    {validation}")

    if attribute.primary_key:
        lines.append("    @Id")
        lines.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")

    column_parts = []

    if not attribute.nullable:
        column_parts.append("nullable = false")

    if column_parts:
        lines.append(f"    @Column({', '.join(column_parts)})")

    lines.append(f"    private {attribute.java_type} {attribute.java_name};")
    return lines


def generate_composite_id_class(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera la clase @Embeddable para entidades con clave primaria compuesta (ej: DetallesPedidoId)."""

    imports = [
        "jakarta.persistence.Embeddable",
        "java.io.Serializable",
        "lombok.AllArgsConstructor",
        "lombok.EqualsAndHashCode",
        "lombok.Getter",
        "lombok.NoArgsConstructor",
        "lombok.Setter",
    ]
    imports.extend(common_imports(entity.pk_attributes))

    fields: list[str] = []
    for attr in entity.pk_attributes:
        fields.append(f"    private {attr.java_type} {attr.java_name};")

    content = "\n".join(
        [
            f"package {base_package}.models;",
            "",
            *[f"import {item};" for item in sorted(set(imports))],
            "",
            "@Embeddable",
            "@Getter",
            "@Setter",
            "@NoArgsConstructor",
            "@AllArgsConstructor",
            "@EqualsAndHashCode",
            f"public class {entity.composite_id_class_name} implements Serializable {{",
            "    private static final long serialVersionUID = 1L;",
            "",
            *fields,
            "}",
            "",
        ]
    )

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/models/{entity.composite_id_class_name}.java",
        language="java",
        content=content,
    )


def generate_model(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el archivo model/Entity.java con anotaciones JPA."""

    imports = [
        "jakarta.persistence.*",
        "lombok.AllArgsConstructor",
        "lombok.Getter",
        "lombok.NoArgsConstructor",
        "lombok.Setter",
    ]

    fields: list[str] = []

    if entity.is_composite_id:
        fields.append("    @EmbeddedId")
        fields.append(f"    private {entity.composite_id_class_name} id;")
        fields.append("")

        non_pk_attributes = [attribute for attribute in entity.attributes if not attribute.primary_key]
        validation_needed = any(validation_annotation(attribute) for attribute in non_pk_attributes)

        if validation_needed:
            imports.extend(["jakarta.validation.constraints.NotBlank", "jakarta.validation.constraints.NotNull"])

        imports.extend(common_imports(non_pk_attributes))

        for attribute in non_pk_attributes:
            fields.extend(field_declaration(attribute))
            fields.append("")
    else:
        validation_needed = any(validation_annotation(attribute) for attribute in entity.attributes)

        if validation_needed:
            imports.extend(["jakarta.validation.constraints.NotBlank", "jakarta.validation.constraints.NotNull"])

        imports.extend(common_imports(entity.attributes))

        for attribute in entity.attributes:
            fields.extend(field_declaration(attribute))
            fields.append("")

    content = "\n".join(
        [
            f"package {base_package}.models;",
            "",
            *[f"import {item};" for item in sorted(set(imports))],
            "",
            "@Entity",
            f'@Table(name = "{entity.table_name}")',
            "@Getter",
            "@Setter",
            "@NoArgsConstructor",
            "@AllArgsConstructor",
            f"public class {entity.class_name} {{",
            *fields,
            "}",
            "",
        ]
    )

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/models/{entity.class_name}.java",
        language="java",
        content=content,
    )



def generate_repository(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el repository que extiende JpaRepository."""

    content = f"""package {base_package}.repositories;

import {base_package}.models.{entity.class_name};
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface {entity.class_name}Repository extends JpaRepository<{entity.class_name}, {entity.id_attribute.java_type}> {{
}}
"""

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/repositories/{entity.class_name}Repository.java",
        language="java",
        content=content,
    )


def dto_field_declaration(attribute: Attribute) -> list[str]:
    """Genera las lineas de un campo para DTO (solo validaciones Jakarta, sin anotaciones JPA @Column/@Id)."""

    lines: list[str] = []
    validation = validation_annotation(attribute)

    if validation:
        lines.append(f"    {validation}")

    lines.append(f"    private {attribute.java_type} {attribute.java_name};")
    return lines


def generate_request_dto(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el DTO usado para crear o actualizar una entidad."""

    attributes = [attribute for attribute in entity.attributes if not attribute.primary_key]
    imports = [
        "lombok.Getter",
        "lombok.Setter",
    ]
    validation_needed = any(validation_annotation(attribute) for attribute in attributes)

    if validation_needed:
        imports.extend(["jakarta.validation.constraints.NotBlank", "jakarta.validation.constraints.NotNull"])

    imports.extend(common_imports(attributes))

    fields: list[str] = []

    for attribute in attributes:
        fields.extend(dto_field_declaration(attribute))
        fields.append("")

    content = "\n".join(
        [
            f"package {base_package}.dto;",
            "",
            *[f"import {item};" for item in sorted(set(imports))],
            "",
            "@Getter",
            "@Setter",
            f"public class {entity.class_name}Request {{",
            *(fields or ["    // Sin campos editables definidos en el diagrama."]),
            "}",
            "",
        ]
    )

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/dto/{entity.class_name}Request.java",
        language="java",
        content=content,
    )


def generate_response_dto(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el DTO usado para responder datos al cliente REST."""

    imports = [
        "lombok.AllArgsConstructor",
        "lombok.Getter",
        "lombok.NoArgsConstructor",
        "lombok.Setter",
    ]
    imports.extend(common_imports(entity.attributes))

    fields = [f"    private {attribute.java_type} {attribute.java_name};" for attribute in entity.attributes]

    content = "\n".join(
        [
            f"package {base_package}.dto;",
            "",
            *[f"import {item};" for item in sorted(set(imports))],
            "",
            "@Getter",
            "@Setter",
            "@NoArgsConstructor",
            "@AllArgsConstructor",
            f"public class {entity.class_name}Response {{",
            *fields,
            "}",
            "",
        ]
    )

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/dto/{entity.class_name}Response.java",
        language="java",
        content=content,
    )


def setter_name(attribute: Attribute) -> str:
    """Construye el nombre del setter Java para un atributo."""

    return f"set{attribute.java_name[:1].upper()}{attribute.java_name[1:]}"


def getter_name(attribute: Attribute) -> str:
    """Construye el nombre del getter Java para un atributo."""

    return f"get{attribute.java_name[:1].upper()}{attribute.java_name[1:]}"


def generate_service(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el service con CRUD completo y conversion a DTO."""

    repo_var = f"{entity.variable_name}Repository"
    request_var = "request"
    model_var = entity.variable_name
    editable_attributes = [attribute for attribute in entity.attributes if not attribute.primary_key]

    request_assignments = [
        f"        {model_var}.{setter_name(attribute)}({request_var}.{getter_name(attribute)}());"
        for attribute in editable_attributes
    ]
    response_args = ", ".join(
        f"{model_var}.{getter_name(attribute)}()" for attribute in entity.attributes
    )

    content = f"""package {base_package}.services;

import {base_package}.dto.{entity.class_name}Request;
import {base_package}.dto.{entity.class_name}Response;
import {base_package}.exceptions.ResourceNotFoundException;
import {base_package}.models.{entity.class_name};
import {base_package}.repositories.{entity.class_name}Repository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class {entity.class_name}Service {{

    private final {entity.class_name}Repository {repo_var};

    public {entity.class_name}Service({entity.class_name}Repository {repo_var}) {{
        this.{repo_var} = {repo_var};
    }}

    public List<{entity.class_name}Response> listar() {{
        return {repo_var}.findAll()
                .stream()
                .map(this::toResponse)
                .toList();
    }}

    public {entity.class_name}Response buscarPorId({entity.id_attribute.java_type} id) {{
        return toResponse(obtenerEntidad(id));
    }}

    public {entity.class_name}Response crear({entity.class_name}Request request) {{
        {entity.class_name} {model_var} = new {entity.class_name}();
{chr(10).join(request_assignments) if request_assignments else "        // No hay campos editables definidos."}
        return toResponse({repo_var}.save({model_var}));
    }}

    public {entity.class_name}Response actualizar({entity.id_attribute.java_type} id, {entity.class_name}Request request) {{
        {entity.class_name} {model_var} = obtenerEntidad(id);
{chr(10).join(request_assignments) if request_assignments else "        // No hay campos editables definidos."}
        return toResponse({repo_var}.save({model_var}));
    }}

    public void eliminar({entity.id_attribute.java_type} id) {{
        {entity.class_name} {model_var} = obtenerEntidad(id);
        {repo_var}.delete({model_var});
    }}

    private {entity.class_name} obtenerEntidad({entity.id_attribute.java_type} id) {{
        return {repo_var}.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("{entity.class_name} no encontrado con id " + id));
    }}

    private {entity.class_name}Response toResponse({entity.class_name} {model_var}) {{
        return new {entity.class_name}Response({response_args});
    }}
}}
"""

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/services/{entity.class_name}Service.java",
        language="java",
        content=content,
    )


def generate_controller(base_package: str, entity: Entity) -> GeneratedFile:
    """Genera el controller REST con endpoints CRUD."""

    service_var = f"{entity.variable_name}Service"

    content = f"""package {base_package}.controllers;

import {base_package}.dto.{entity.class_name}Request;
import {base_package}.dto.{entity.class_name}Response;
import {base_package}.services.{entity.class_name}Service;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/{entity.route_name}")
public class {entity.class_name}Controller {{

    private final {entity.class_name}Service {service_var};

    public {entity.class_name}Controller({entity.class_name}Service {service_var}) {{
        this.{service_var} = {service_var};
    }}

    @GetMapping
    public ResponseEntity<List<{entity.class_name}Response>> listar() {{
        return ResponseEntity.ok({service_var}.listar());
    }}

    @GetMapping("/{{id}}")
    public ResponseEntity<{entity.class_name}Response> buscarPorId(@PathVariable {entity.id_attribute.java_type} id) {{
        return ResponseEntity.ok({service_var}.buscarPorId(id));
    }}

    @PostMapping
    public ResponseEntity<{entity.class_name}Response> crear(@Valid @RequestBody {entity.class_name}Request request) {{
        return ResponseEntity.status(HttpStatus.CREATED).body({service_var}.crear(request));
    }}

    @PutMapping("/{{id}}")
    public ResponseEntity<{entity.class_name}Response> actualizar(
            @PathVariable {entity.id_attribute.java_type} id,
            @Valid @RequestBody {entity.class_name}Request request
    ) {{
        return ResponseEntity.ok({service_var}.actualizar(id, request));
    }}

    @DeleteMapping("/{{id}}")
    public ResponseEntity<Void> eliminar(@PathVariable {entity.id_attribute.java_type} id) {{
        {service_var}.eliminar(id);
        return ResponseEntity.noContent().build();
    }}
}}
"""

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/controllers/{entity.class_name}Controller.java",
        language="java",
        content=content,
    )


def generate_application(base_package: str, project_name: str) -> GeneratedFile:
    """Genera la clase principal de Spring Boot."""

    class_name = f"{to_pascal_case(project_name)}Application"

    content = f"""package {base_package};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {class_name} {{

    public static void main(String[] args) {{
        SpringApplication.run({class_name}.class, args);
    }}
}}
"""

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/{class_name}.java",
        language="java",
        content=content,
    )


def generate_backend_metadata_controller(
    base_package: str,
    project_name: str,
    entities: list[Entity],
) -> GeneratedFile:
    """Genera los endpoints usados por el movil para detectar y describir el backend."""

    schema = {
        "proyecto": project_name,
        "version": "1.0",
        "entidades": [
            {
                "nombre": entity.name,
                "endpoint": f"/api/{entity.route_name}",
                "id": {
                    "nombre": entity.id_attribute.java_name,
                    "type": map_schema_type(entity.id_attribute.java_type),
                    "generado": entity.generated_id,
                    "compuesto": entity.is_composite_id,
                },
                "atributos": {
                    attribute.java_name: {
                        "type": map_schema_type(attribute.java_type),
                        "required": not attribute.nullable,
                    }
                    for attribute in entity.attributes
                    if not attribute.primary_key
                },
                "operaciones": [
                    "CREAR",
                    "LISTAR",
                    "OBTENER",
                    "ACTUALIZAR",
                    "ELIMINAR",
                ],
            }
            for entity in entities
        ],
    }
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    project_literal = json.dumps(project_name, ensure_ascii=False)

    content = f'''package {base_package}.controllers;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class BackendMetadataController {{

    private static final String SCHEMA_JSON = """
{schema_json}
            """;

    @GetMapping("/health")
    public Map<String, Object> health() {{
        return Map.of(
                "status", "UP",
                "project", {project_literal},
                "schemaVersion", "1.0"
        );
    }}

    @GetMapping(value = "/schema", produces = MediaType.APPLICATION_JSON_VALUE)
    public String schema() {{
        return SCHEMA_JSON;
    }}
}}
'''

    return GeneratedFile(
        path=f"src/main/java/{package_path(base_package)}/controllers/BackendMetadataController.java",
        language="java",
        content=content,
    )


def generate_common_files(base_package: str, project_name: str, database_name: str) -> list[GeneratedFile]:
    """Genera archivos comunes: pom.xml, properties, README, SQL, CORS y errores."""

    project_literal = json.dumps(project_name, ensure_ascii=False)

    pom = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>{base_package}</groupId>
    <artifactId>{project_name}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>{project_name}</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.jmdns</groupId>
            <artifactId>jmdns</artifactId>
            <version>3.6.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

    properties = f"""spring.application.name={project_name}
spring.datasource.url=jdbc:postgresql://localhost:5432/{database_name}
spring.datasource.username=postgres
spring.datasource.password=postgres

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect

server.address=0.0.0.0
server.port=${{SERVER_PORT:8086}}
drawschema.discovery.enabled=true
"""

    database_sql = f"CREATE DATABASE {database_name};\n"

    readme = f"""# {project_name}

Backend Spring Boot generado por DrawSchemaAI.

## Requisitos

- Java 17 o superior
- Maven
- PostgreSQL

## Crear base de datos

```sql
CREATE DATABASE {database_name};
```

## Configurar conexion

Edita `src/main/resources/application.properties` si tu usuario o password de PostgreSQL son distintos.

## Ejecutar

```bash
mvn spring-boot:run
```

## Endpoints

Los controladores generados exponen rutas REST bajo `/api`.
"""

    resource_not_found = f"""package {base_package}.exceptions;

public class ResourceNotFoundException extends RuntimeException {{

    public ResourceNotFoundException(String message) {{
        super(message);
    }}
}}
"""

    global_exception = f"""package {base_package}.exceptions;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {{

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<Map<String, Object>> handleNotFound(ResourceNotFoundException exception) {{
        Map<String, Object> body = new HashMap<>();
        body.put("timestamp", LocalDateTime.now());
        body.put("status", 404);
        body.put("message", exception.getMessage());
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }}

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException exception) {{
        Map<String, Object> body = new HashMap<>();
        body.put("timestamp", LocalDateTime.now());
        body.put("status", 400);
        body.put("message", "Error de validacion");
        body.put("errors", exception.getBindingResult().getFieldErrors()
                .stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .toList());
        return ResponseEntity.badRequest().body(body);
    }}
}}
"""

    cors_config = f"""package {base_package}.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {{

    @Override
    public void addCorsMappings(CorsRegistry registry) {{
        registry.addMapping("/api/**")
                .allowedOrigins("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*");
    }}
}}
"""

    mdns_config = f"""package {base_package}.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

import javax.jmdns.JmDNS;
import javax.jmdns.ServiceInfo;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

@Component
public class MdnsServicePublisher
        implements ApplicationListener<WebServerInitializedEvent>, DisposableBean {{

    private static final Logger log = LoggerFactory.getLogger(MdnsServicePublisher.class);
    private static final String SERVICE_TYPE = "_drawschema._tcp.local.";

    @Value("${{drawschema.discovery.enabled:true}}")
    private boolean enabled;

    private volatile JmDNS jmDNS;

    @Override
    public void onApplicationEvent(WebServerInitializedEvent event) {{
        if (!enabled || jmDNS != null) return;

        Thread publisher = new Thread(() -> publish(event.getWebServer().getPort()), "drawschema-mdns");
        publisher.setDaemon(true);
        publisher.start();
    }}

    private void publish(int port) {{
        try {{
            InetAddress address = findLanAddress();
            Map<String, String> properties = new HashMap<>();
            properties.put("project", {project_literal});
            properties.put("schemaVersion", "1.0");
            properties.put("healthPath", "/api/health");
            properties.put("schemaPath", "/api/schema");

            JmDNS instance = JmDNS.create(address);
            ServiceInfo service = ServiceInfo.create(
                    SERVICE_TYPE,
                    {project_literal},
                    port,
                    0,
                    0,
                    properties
            );
            instance.registerService(service);
            jmDNS = instance;
            log.info("DrawSchema disponible en http://{{}}:{{}}", address.getHostAddress(), port);
        }} catch (Exception exception) {{
            log.warn("No se pudo publicar DrawSchema por mDNS: {{}}", exception.getMessage());
        }}
    }}

    private InetAddress findLanAddress() throws Exception {{
        try (DatagramSocket socket = new DatagramSocket()) {{
            socket.connect(new InetSocketAddress("8.8.8.8", 53));
            InetAddress routedAddress = socket.getLocalAddress();
            if (routedAddress instanceof Inet4Address
                    && !routedAddress.isAnyLocalAddress()
                    && !routedAddress.isLoopbackAddress()) {{
                return routedAddress;
            }}
        }} catch (Exception ignored) {{
            // Sin ruta de salida: se intenta con las interfaces disponibles.
        }}

        InetAddress fallback = null;
        for (NetworkInterface network : Collections.list(NetworkInterface.getNetworkInterfaces())) {{
            if (!network.isUp() || network.isLoopback() || network.isVirtual()) continue;
            for (InetAddress address : Collections.list(network.getInetAddresses())) {{
                if (!(address instanceof Inet4Address) || address.isLoopbackAddress()) continue;
                if (address.isSiteLocalAddress()) return address;
                if (!address.isLinkLocalAddress()) fallback = address;
            }}
        }}
        if (fallback != null) return fallback;
        throw new IllegalStateException("No se encontro una direccion IPv4 de red local");
    }}

    @Override
    public void destroy() throws Exception {{
        JmDNS instance = jmDNS;
        if (instance != null) {{
            instance.unregisterAllServices();
            instance.close();
        }}
    }}
}}
"""

    return [
        GeneratedFile(path="pom.xml", language="xml", content=pom),
        GeneratedFile(path="README.md", language="markdown", content=readme),
        GeneratedFile(path="database.sql", language="sql", content=database_sql),
        GeneratedFile(
            path="src/main/resources/application.properties",
            language="properties",
            content=properties,
        ),
        GeneratedFile(
            path=f"src/main/java/{package_path(base_package)}/exceptions/ResourceNotFoundException.java",
            language="java",
            content=resource_not_found,
        ),
        GeneratedFile(
            path=f"src/main/java/{package_path(base_package)}/exceptions/GlobalExceptionHandler.java",
            language="java",
            content=global_exception,
        ),
        GeneratedFile(
            path=f"src/main/java/{package_path(base_package)}/config/CorsConfig.java",
            language="java",
            content=cors_config,
        ),
        GeneratedFile(
            path=f"src/main/java/{package_path(base_package)}/config/MdnsServicePublisher.java",
            language="java",
            content=mdns_config,
        ),
    ]


def build_spring_boot_project(
    context: dict[str, Any],
    project_name: str,
    base_package: str,
    database_name: str,
) -> tuple[list[GeneratedFile], list[str]]:
    """Orquesta la generacion completa del proyecto Spring Boot."""

    entities, warnings = parse_entities(context)
    files: list[GeneratedFile] = []

    files.extend(generate_common_files(base_package, project_name, database_name))
    files.append(generate_application(base_package, project_name))
    files.append(generate_backend_metadata_controller(base_package, project_name, entities))

    for entity in entities:
        if entity.is_composite_id:
            files.append(generate_composite_id_class(base_package, entity))
        files.append(generate_model(base_package, entity))
        files.append(generate_repository(base_package, entity))
        files.append(generate_request_dto(base_package, entity))
        files.append(generate_response_dto(base_package, entity))
        files.append(generate_service(base_package, entity))
        files.append(generate_controller(base_package, entity))


    return files, warnings
