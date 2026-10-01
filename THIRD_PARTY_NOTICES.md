# Third-Party Software Notices and Information

This project adapts architectural patterns, procedural steps, and progressive disclosure
conventions from the following third-party open-source software:

Every upstream named in a `## Procedencia` section of `library/**/SKILL.md` has an entry here, and
the suite fails when one does not.

---

## obra/superpowers

**Source:** https://github.com/obra/superpowers  
**Commit:** `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`  
**License:** MIT License  
**Copyright:** Copyright (c) 2025 Jesse Vincent  

### Adapted Content

- The procedural capabilities behind the 21 skills in `library/base/` and the four in
  `library/catalog/`. Each skill declares what it took in its own `## Procedencia` section.

### Excluded Content

- These skills are this framework's own reimplementation, written for this repository. No text is
  copied or translated: what is taken is the capability and the procedure, not the wording.

### MIT License Text

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

### Adapted Content

- The capabilities and procedures of the same base and catalog skills, together with
  `obra/superpowers`. Each skill names both upstreams in its own `## Procedencia` section.

### Excluded Content

- No text copied or translated. `idea-refine`, `interview-me` and `using-agent-skills` were
  evaluated and rejected as meta or interactive, without universal value.

### MIT License Text

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

### Adapted Patterns

- Nine procedural capabilities: scope, audit, architect, document, test, develop, debug, sync, and check.
- Progressive disclosure directory layout (`modes/`, `internal/`, `references/`, `templates/`, `adapters/`).
- Context budget enforcement and hot-path limits for agent routers.

### Excluded Content

- No product-specific final modes, slash-command workflows, auto-install scripts, npx/MCP dependencies, Claude/web/Git tool bindings, or non-functional editorial rules are copied or redistributed.

### MIT License Text

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
