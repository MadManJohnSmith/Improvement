# Avisos de software de terceros e información

**English:** [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | **Español**

Este proyecto adapta patrones arquitectónicos, pasos procedimentales y convenciones de
divulgación progresiva del siguiente software de código abierto de terceros:

Cada upstream nombrado en una sección `## Procedencia` de `library/**/SKILL.md` tiene aquí una
entrada, y la suite falla cuando no la tiene.

---

## obra/superpowers

**Source:** https://github.com/obra/superpowers
**Commit:** `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`
**License:** MIT License
**Copyright:** Copyright (c) 2025 Jesse Vincent

### Contenido adaptado

- Las capacidades procedimentales de las 21 skills de `library/base/` y las cuatro de
  `library/catalog/`. Cada skill declara qué tomó en su propia sección `## Procedencia`.

### Contenido excluido

- Estas skills son una reimplementación propia de este framework, escrita para este repositorio.
  No se copia ni traduce ningún texto: lo que se toma es la capacidad y el procedimiento, no la
  redacción.

### Texto de la licencia MIT

```text
MIT License
Copyright (c) 2025 Jesse Vincent
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## addyosmani/agent-skills

**Source:** https://github.com/addyosmani/agent-skills
**Commit:** `be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39`
**License:** MIT License
**Copyright:** Copyright (c) 2025 Addy Osmani

### Contenido adaptado

- Las capacidades y los procedimientos de las mismas skills base y de catálogo, junto a
  `obra/superpowers`. Cada skill nombra ambos upstream en su propia sección `## Procedencia`.

### Contenido excluido

- No se copia ni traduce ningún texto. `idea-refine`, `interview-me` y `using-agent-skills` se
  evaluaron y se rechazaron por ser meta o interactivas, sin valor universal.

### Texto de la licencia MIT

```text
MIT License
Copyright (c) 2025 Addy Osmani
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## jsmastery-pro/skills

**Source:** https://github.com/jsmastery-pro/skills
**Commit:** `43b69e44c9ca905fe3a3418ccdf4102255e20d40` (2026-08-07)
**License:** MIT License

### Patrones adaptados

- Nueve capacidades procedimentales: scope, audit, architect, document, test, develop, debug, sync y check.
- Esquema de directorios de divulgación progresiva (`modes/`, `internal/`, `references/`, `templates/`, `adapters/`).
- Aplicación del presupuesto de contexto y de los límites del camino caliente de los routers de agentes.

### Contenido excluido

- No se copian ni redistribuyen modos finales específicos de producto, flujos de slash-command,
  scripts de autoinstalación, dependencias npx/MCP, enlaces con Claude/web/Git ni reglas
  editoriales no funcionales.

### Texto de la licencia MIT

```text
MIT License

Copyright (c) 2026 JS Mastery

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
