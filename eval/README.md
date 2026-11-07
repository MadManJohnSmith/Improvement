# eval: caso remoto de Creator

Artefactos de configuración del caso de evaluación remota del Creator,
versionados para que cualquier runner pueda repetir el caso (issue #14,
spec #11). El contrato de ambos lo mantiene `tests/test_eval_config.py`.

- `criteria-remote-creator.json` — criterio pre-registrado del caso. Lo
  consume `scripts/creator_eval.py` tal cual (`require_criteria`); el `id`
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
        -e "s|@DSH_PROFILE_API@|$PROVIDER_API|g" \
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
- `$PROVIDER_API`: canal de la API que habla el endpoint
  (`openai-completions`, el OpenAI estándar, u `openai-responses`, el
  validado con omniroute); entrada del workflow.

## Modo keyless

Verificado contra el endpoint público de opencode: su tier gratuito solo
acepta peticiones **sin** cabecera de autenticación (cualquier Bearer no
vacío responde `authentication_error`; sin cabecera, la petición se
evalúa contra el cupo anónimo), pero pi-ai de DSH siempre exige una
credencial (`No API key for provider`). Por eso `auth=keyless` aplica el
patrón OmniRoute: un proxy local del runner
(`eval/keyless_proxy.py`, solo stdlib) se interpone entre DSH y el
proveedor, elimina la cabecera `Authorization` y reenvía al upstream
retransmitiendo el stream por trozos. El workflow lo lanza antes del
render, publica el endpoint local en `PROVIDER_ENDPOINT`
(`http://127.0.0.1:8091`) y el perfil renderizado lo usa como baseURL;
el despacho exporta como credencial un señuelo (`anonymous`) que pi-ai
exige y el proxy elimina. Su contrato lo mantiene
`tests/test_keyless_proxy.py` (stub de upstream incluido).

Ejemplo con el tier gratuito de opencode (valores del endpoint público
`/inference/v1/models`): `$PROVIDER_API=openai-completions`,
`$BASE_URL=https://opencode.ai/inference/openai/v1`,
`$MODEL=deepseek-v4.1-flash-free`, `$CONTEXT_WINDOW=200000`,
`$MAX_TOKENS=32000`. El límite del tier gratuito es por peticiones, no
por tokens: si el run lo agota, el journal y el log del run lo muestran
(`FreeUsageLimitError`) y el caso queda como evidencia, no como fallo
del prompt.

Con `auth=secret` no hay proxy: la URL pública va directa al perfil y
`apiKeyEnv: DSH_PROVIDER_API_KEY` es el **nombre** de la variable de
entorno cuyo valor exporta el runner desde el secreto del repositorio
antes de lanzar DSH; el perfil solo la referencia.

Antes de `gh secret set`, valida que el valor sea una credencial real y no
una referencia de placeholder (`refs.*` del YAML de credenciales de DSH no
es una clave: el primer secreto fijado fue exactamente eso — GitHub enmascaró
cada guion del log — y hubo que borrarlo):

```console
$ printf '%s' "$VALOR" | grep -Eq '^(refs\.|<|\$)' && echo "PLACEHOLDER, no fijar"
```

Si el comando imprime el aviso, el valor no es una clave: busca la credencial
real en la fuente del proveedor.
