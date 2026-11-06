# eval: caso remoto de Creator

Artefactos de configuración del caso de evaluación remota del Creator,
versionados para que cualquier runner pueda repetir el caso (issue #14,
spec #11). El contrato de ambos lo mantiene `tests/test_eval_config.py`.

- `criteria-remote-creator.json` — criterio pre-registrado del caso. Lo
  consume `scripts/creator_eval.py` tal cual (`_require_criteria`); el `id`
  del caso llega al reporte (`report.json` → `case`).
- `profile-dsh.patch.yml` — plantilla del patch de perfil de DSH 0.2.1,
  en el formato `cordis.patch.yml` de un bundle de perfil (array YAML de
  entradas del loader: `llm-pi-ai` + `agent-default-model`).

## Relleno de la plantilla

La plantilla declara puntos de relleno `@NOMBRE@`, deliberadamente YAML
inválido: una copia sin rellenar no puede cargarla nadie por descuido. El
workflow la copia como `cordis.patch.yml` dentro del bundle de perfil y
sustituye los marcadores antes de instalarlo, por ejemplo:

    sed -e "s|@DSH_PROFILE_PROVIDER@|$PROVIDER|g" \
        -e "s|@DSH_PROFILE_BASE_URL@|$BASE_URL|g" \
        -e "s|@DSH_PROFILE_MODEL@|$MODEL|g" \
        -e "s|@DSH_PROFILE_CONTEXT_WINDOW@|$CONTEXT_WINDOW|g" \
        -e "s|@DSH_PROFILE_MAX_TOKENS@|$MAX_TOKENS|g" \
        eval/profile-dsh.patch.yml > "$PROFILE_DIR/cordis.patch.yml"

- `$PROVIDER`: nombre del proveedor dentro del perfil (identidad interna
  de DSH); lo elige quien despacha.
- `$BASE_URL`: URL base pública del proveedor (https), entrada del
  workflow.
- `$MODEL`, `$CONTEXT_WINDOW`, `$MAX_TOKENS`: modelo y sus ventanas de
  contexto y salida; entradas del workflow.

La clave nunca pasa por el repositorio: `apiKeyEnv: DSH_PROVIDER_API_KEY`
es el **nombre** de la variable de entorno cuyo valor exporta el runner
desde el secreto del repositorio antes de lanzar DSH; el perfil solo la
referencia. El canal fijado es `api: openai-responses`, el validado en el
caso observado.
