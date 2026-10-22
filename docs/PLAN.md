# Plano — aneel-regulatory-rag (v3, aprovado)

> Cópia versionada do plano aprovado (v3, com todos os ajustes das três rodadas de revisão). O texto do plano abaixo da seção **Status** é o aprovado; mudanças posteriores são registradas em **Status → Decisões tomadas fora do plano**, que prevalecem sobre o texto original.

> **Corte de publicação = Fases 0–5 + README (Fase 7).** A Fase 6 (observabilidade, API e demo) é opcional, e a Fase 8 é bônus.

## Status

_Atualizado em 2026-10-22._

| Fase | Estado | Referência |
|---|---|---|
| 0 — Scaffold | **concluída** (merge em 2026-10-20) | PR #1, commit `4c3bd1b` |
| 1 — Ingestão + parser | **em revisão** | PR #3 (branch `phase-1`) |
| 2–5 | pendentes | — |
| 6 (opcional), 7, 8 (bônus) | pendentes | — |

### Decisões tomadas fora do plano

| # | Decisão | Onde está registrada |
|---|---|---|
| 1 | **A âncora `#articleN` não funciona** no leis.org ao vivo: o span só tem `data-summary-id` e o sumário rola via JS. Em lugar dela, `source_url` é um **text fragment** (`#:~:text=<prefixo>`), descrito abaixo. Isto substitui o "`source_url` se a âncora funcionar" da Fase 1 e a linha de risco correspondente. | ADR-002 |
| 2 | Regras do `source_url`: o prefixo tem 6 palavras (`corpus.fragment_min_words`) e não inclui o rótulo do dispositivo. Ele cresce até ser único no texto inteiro da página, **incluindo o texto riscado**. Os caracteres `-`, `,` e `&` vão escapados. Unit revogado e unit sem prefixo único recebem `None`. A função pura (`ingest/source_url.py`, 18 testes) foi implementada já na Fase 0; a ligação com os units fica para a Fase 1. | ADR-002, PR #1 |
| 3 | **Links abertos a frio não destacam o trecho:** o desafio do Cloudflare descarta o fragmento e a página abre no topo. O destaque só funciona em Chromium com a página já aberta. Por isso, a citação sempre mostra o ID do dispositivo e a quote, e o link é só uma conveniência. | ADR-002, README |
| 4 | O Qdrant está fixado em `v1.19.1`, para casar com o `qdrant-client` 1.19.1. | `docker-compose.yml` |
| 5 | O `make help` usa `scripts/make_help.py` em vez de grep/awk, para funcionar no PowerShell e no Git Bash. | `Makefile` |
| 6 | Os smoke tests de modelos rodam com `make smoke` (marker `smoke`, excluído por `addopts`) e precisam do `.env` preenchido. | `pyproject.toml`, PR #1 |
| 7 | **O runner do CI está fixado em `ubuntu-24.04`** por reprodutibilidade. As actions usam a última versão major em Node 24: `actions/checkout@v7`, `astral-sh/setup-uv@v10.3.0` e `gitleaks/gitleaks-action@v3`. O ADR-005 foi criado antes da Fase 5 para registrar isso; a parte de avaliação fica para a Fase 5. | ADR-005 |
| 8 | O único artifact do CI é o `gitleaks-results.sarif`, com os segredos ocultados (`--redact`). Ele não contém o `.env` nem nada de `data/raw/`. | ADR-005, PR #1 |
| 9 | A seção "Status" deste documento e o `CLAUDE.md` na raiz registram as regras permanentes do projeto. | PR #2 |
| 10 | **Correções da inspeção da Fase 1** aos números da seção "O que a inspeção do HTML mostrou":<br>• os IDs têm ponto (`article23.`);<br>• há 156 "Redação dada" + 204 "Redação acrescida" (o "339" contava `<b>` com anotação);<br>• há 16 `<img>` no texto (e não 28);<br>• não existe Subseção;<br>• o Art. 35 vigente não tem `span.artigo`. | ADR-002 |
| 11 | **O `<br>` simples também separa dispositivos.**<br>• Um unit começa numa linha com rótulo aceito pela sequência do pai (os rótulos riscados contam).<br>• Linhas sem rótulo são continuação.<br>• Rótulos fora de sequência viram continuação e vão para o relatório (o único caso é "C - é o consumo", no Art. 73-A). | ADR-002 |
| 12 | **Vigência:**<br>• todo texto riscado é descartado, exceto quando há "(Revogado…)" logo depois, caso em que o bloco riscado contíguo fica `revoked`;<br>• o status vem da anotação ("dada" → `amended`, "acrescida" → `added`);<br>• uma linha em negrito sem anotação herda a próxima anotação do bloco;<br>• a regra "`<b>` sem anotação = added" do plano não tem casos reais. | ADR-002 |
| 13 | **Citações de outras normas** (Arts. 672–676) ficam em modo citação até "(NR)" e geram `quotes_other_norm: true`, sem perder a indexação. O fallback `^Art. N` só vale fora de citação e para o sucessor do artigo anterior. | ADR-002 |
| 14 | **Defeitos do texto oficial tratados e reportados:**<br>• rótulo dobrado (Art. 250);<br>• `<br>` perdido antes do § 2º (Art. 666);<br>• • alínea repetida e alínea ausente (Art. 668, III).<br>O Art. 485 **não** é defeito: os §§ 5º e 6º estão na mesma linha do § 4º, sem `<br>`. Numa lacuna de sequência, o parser procura o rótulo faltante dentro do unit anterior (seguido de palavra maiúscula) e divide ali; cada divisão vai para a seção "Inline label repairs" do relatório. No corpus inteiro, só o Art. 485 é reparado assim. | `ingest_report.md`, ADR-002 |
| 15 | **Anexos:**<br>• o I vai por cláusula, os II e III com um unit cada, e o IV com um unit por linha da tabela;<br>• os anexos não entram no dataset do MVP;<br>• o `amended_by` registra só a versão vigente. | ADR-002 |
| 16 | **O texto é salvo em NFC.** NFKC e casefold só valem na comparação de citações (Fase 3). | ADR-002 |
| 17 | **Módulos além da lista do plano:**<br>• `ingest/labels.py` (rótulos, compartilhado com `source_url.py`) e `ingest/pipeline.py`;<br>• `scripts/cut_fixtures.py`, que recorta as fixtures reais do recorte;<br>• os alvos `make extract` e `make fixtures`. | PR #3 |

---

## Contexto

O repositório está praticamente vazio: tem 1 commit inicial, `.gitignore` (template Python), `.env.example` e `config/default.yaml` já esboçados. O objetivo é um RAG de portfólio sobre a REN 1.000/2021 com citação obrigatória por dispositivo, abstenção e avaliação reprodutível. O plano segue as fases 0–8 do pedido. **Execução direta, uma fase por vez.** Cada fase vai numa branch `phase-N`, segue com push e PR, e o CI precisa ficar verde. Você revisa e faz o merge. A passada do revisor (Edna) no fim de cada fase é opcional.

### Fonte do corpus (correção de premissa)

- A fonte oficial é o **leis.org/aneel**: o site do governo redireciona para lá. O insumo principal é `data/raw/ren1000.html`, um snapshot manual. O PDF exportado em `data/raw/*.pdf` serve só de referência para conferência humana.
- **Versionamos SOMENTE o recorte `data/raw/ren1000_law_content.html`.** É o `#law-content` sem template, scripts, figuras e lista de normas relacionadas, e **a ingestão parte dele**. O HTML completo e o PDF ficam fora do git. O recorte é gerado por `python -m aneel_rag.ingest.extract_law_content` a partir do HTML completo, e esse passo é determinístico.
- `data/raw/SOURCE.md` (commitado) registra a URL, a data do snapshot, o SHA-256 do HTML completo, o do recorte e o do PDF, e a última REN anotada (hoje a 1162/2026, de 02/06/2026). O **SHA-256 do corpus** é o do recorte, e é esse que entra no relatório de avaliação.

### O que a inspeção do HTML mostrou (só leitura, com bs4 e lxml temporários via `uv run --no-project`)

- **O texto da norma fica em `div#law-content.aneel-content`.** É texto plano separado por `<br><br>`, sem um elemento por dispositivo. Só o artigo e os títulos têm marcação:
  - artigo: `<span class="artigo" data-summary-type="article" data-summary-id="article23">Art. 23</span>`
  - títulos: `<span class="titulo" data-summary-type="title">` com "TÍTULO I<br>PARTE GERAL", Capítulo, Seção.
- **Contagens:** 745 spans de artigo, com 744 IDs únicos (`article157` aparece duas vezes). O último é o Art. 679. Há 42 artigos com letra (`48-A`, `96-A`…). Alguns IDs têm sujeira, como `article675.` ou `article371-A ` com espaço, e precisam ser normalizados.
- **Texto superado:** vem em `<s>…</s>`. São 170 ocorrências, sendo 28 delas artigos inteiros riscados, o que explica o `article157` duplicado.
- **Texto vigente alterado ou incluído:** vem em `<b>…</b>` (fonte azul na tela). São 363 `<b>` na área da norma; 339 trazem "(Redação dada pela Resolução Normativa nº X)". Os demais são inclusões sem anotação ou notas.
- **Revogação:** o texto riscado (`<s>§ 2º …</s>`) vem seguido de "(Revogado pela Resolução Normativa nº 1059/2023)" fora do `<s>`. São 12 casos. Ou seja, um dispositivo revogado é um `<s>` sem substituto e com essa anotação.
- **Notas de vigência:** "(Vide Despacho nº 1.731/2025 …)", "(Vide afastamento do desconto …)" e "(Suspensos os efeitos … Despacho nº 2006/2024)" aparecem no preâmbulo e no meio de dispositivos. Elas viram metadado `notes` do unit, e não texto de busca.
- **Anotações e links:** as anotações têm links `a.link_law` com `data-original-title` (data e ementa da norma alteradora). Com isso dá para preencher `amended_by` com número e data.
- **Fim do texto normativo:** depois do Art. 679 vêm assinatura, notas do DOU, Anexos I–IV (contratos e formulários), 2 tabelas (`table-wrapper`, uma delas uma tabela de prazos, por exemplo "art. 76, § 5º | 10 dias úteis") e, ainda dentro de `#law-content`, a **lista de normas relacionadas**, com lixo de template ("SELECT status_consolidacao FROM leismeta…"). Esse bloco precisa ser cortado.
- **Figuras:** há 28 `<img>`, com arquivos em `data/raw/ren1000_files/`, como `RESNORM-1000-2021+figura+N.png`. Provavelmente são fórmulas, e o conteúdo delas não está no texto.
- **Não existe número de página no HTML, e não vamos mapear o PDF (D13).** O campo `page` vira `source_anchor` (o id do artigo e o ordinal do dispositivo). Os artigos têm `id="article1º"` no DOM salvo. Na Fase 1 verifico se `<URL>#article23` (com percent-encoding de `º`) rola até o artigo no leis.org ao vivo. Se rolar, cada unit ganha também `source_url` clicável; se não, fica só o `source_anchor`, e o motivo vai para o ADR-002.
- **Ambiente:** o Python do sistema é 3.14 e o uv 0.12.5 está instalado. Docker: você disse que está instalado, mas ainda não aparece no PATH desta sessão; confiro na Fase 0. `make` e `gh` **não** estão no PATH (veja D2 e D10).

---

## Decisões técnicas (viram ADRs)

| ADR | Decisão |
|---|---|
| 001 | **uv** com env próprio do projeto (`.venv` local) e **Python 3.12** fixado em `.python-version` e `requires-python = ">=3.12,<3.13"`, por compatibilidade com torch, FlagEmbedding e RAGAS. O `uv.lock` é commitado. |
| 002 | **Parsing estrutural sobre o HTML** e chunking estrutural. O parser usa a marcação real: âncoras `span.artigo` e `span.titulo`, `<s>` para texto superado ou revogado e `<b>` para texto vigente alterado ou incluído. A regex fica só para o que não tem marcação (§, inciso, alínea, anotações). Chunk: um por artigo; artigos longos são divididos por § com prefixo de caput e caminho hierárquico. O chunking fixo com overlap existe só para a ablação. O ADR registra por que HTML em vez de PDF: há marcação semântica de vigência, e o PDF exigiria detectar o risco por geometria e juntar o número do artigo por posição. |
| 003 | Busca híbrida com Qdrant (denso + esparso do bge-m3), fusão RRF nativa (`prefetch` e `FusionQuery(RRF)`) e cross-encoder de top-20 para top-5. Por padrão, o filtro de payload exclui `status=revoked` e `doc_type=annex`. |
| 004 | Validação determinística e política de citação conforme D6 (detalhada na Fase 3). |
| 005 | O CI fica leve: ruff, pytest com fixtures HTML, Qdrant `:memory:` e embeddings fake, sem modelos e sem LLM. A avaliação completa roda localmente e o relatório é commitado. |
| 006 | `LLMProvider` como protocolo, com a fábrica `get_chat_model(role, cfg)`, onde `role` é `generator` ou `judge`, devolvendo `ChatOpenAI(base_url, api_key, model)`. Gemini e llama.cpp diferem só na config. A saída estruturada usa `json_schema`, com fallback para `json_mode` e validação Pydantic. **Modelos:** o `generator` é `gemini-3.8-flash` (GA, ID fixo) e também é usado em `grade_context` no MVP; o `judge` é `gemini-3.1-pro-preview`. O ADR registra: por que o juiz é um Pro em preview (não existe Pro estável atual); o risco (o ID pode mudar ou ser descontinuado, e o comportamento pode variar); e as mitigações (cache do juiz por `judge_model_id`, calibração juiz × humano, e o ID gravado em todo relatório). **É proibido usar aliases `-latest`**: o `settings.py` rejeita qualquer ID de modelo que termine em `-latest` (com teste). |

**Config vs. env:**
- `config/*.yaml` guarda tudo o que afeta resultado: k, modelos (`generator: gemini-3.8-flash`, `judge: gemini-3.1-pro-preview`), estratégia de chunking, temperatura, limites de quote e prompts versionados.
- `.env` guarda só segredos e endpoints. Os nomes de modelo saem do `.env`, e o `.env.example` é atualizado.
- O `confighash` é o SHA-256 do yaml resolvido (sem segredos), somado ao hash dos prompts e ao SHA-256 do corpus.

## Estrutura de diretórios

```
src/aneel_rag/{config,ingest,chunking,retrieval,graph,llm,observability,api}/   # src layout
eval/{dataset.jsonl,draft_questions.py,run_eval.py,metrics.py,ragas_metrics.py,thresholds.yaml,reports/}
config/{default.yaml, ablations/*.yaml, providers/*.yaml}
prompts/{grade_context.md,generate.md,draft_questions.md}
app/demo.py
tests/{fixtures/html/,unit/}
data/raw/{ren1000.html, ren1000_files/, *.pdf}               # fora do git
data/raw/{ren1000_law_content.html, SOURCE.md}               # versionados
data/{processed/,cache/}                                      # ignorados
docs/adr/
docker-compose.yml  Makefile  .pre-commit-config.yaml  .github/workflows/ci.yml  pyproject.toml
```

`.gitignore`: acrescentar `data/raw/*`, `!data/raw/SOURCE.md`, `!data/raw/ren1000_law_content.html`, `data/processed/`, `data/cache/` e `.venv/`. Os recortes do HTML usados como fixture ficam em `tests/fixtures/html/` e são versionados, já que o texto da norma é público.

---

## Fase 0 — Scaffold

**Arquivos:**
- `pyproject.toml`, `uv.lock`, `.python-version` (3.12)
- `src/aneel_rag/**/__init__.py`
- `src/aneel_rag/config/settings.py`
- `.pre-commit-config.yaml`: ruff, ruff-format, **gitleaks**, end-of-file e trailing-whitespace
- `.github/workflows/ci.yml`, `Makefile`, `docker-compose.yml`
- `tests/unit/test_config.py`
- `docs/adr/001-dependency-manager.md`
- `README.md` provisório com o aviso de projeto pessoal
- `data/raw/SOURCE.md`
- ajustes no `.gitignore` e no `.env.example`

Componentes:
- `settings.py`: lê o yaml, valida com Pydantic e sobrepõe os segredos vindos do env com pydantic-settings. Também expõe `config_hash()` e `corpus_sha256()`.
- `docker-compose.yml`: só o Qdrant (versão fixada e volume nomeado). O Langfuse é Cloud, não entra no compose.
- Grupos de dependências: `ml` (torch CPU e FlagEmbedding), `eval` (ragas) e `demo` (gradio). O CI usa `uv sync --frozen` sem esses grupos.
- **PyTorch só CPU:** `[[tool.uv.index]] name="pytorch-cpu" url="https://download.pytorch.org/whl/cpu" explicit=true` e `[tool.uv.sources] torch = { index = "pytorch-cpu" }`, para nunca baixar CUDA.
- **O Makefile é a única fonte de tarefas** (o `make` será instalado via winget). Ele chama `uv run python -m …` e não usa recursos específicos de shell, para rodar no Git Bash e no CI.
- **Smoke test dos modelos** (`tests/smoke/test_llm_models.py`, marcado `@pytest.mark.smoke` e pulado no CI e sem `LLM_API_KEY`): lista `GET /models` no endpoint e falha se o `generator` ou o `judge` configurados não existirem. Alvo: `make smoke`.
- **PRs:** a branch `phase-N` vai por push e o PR é aberto por mim via `gh pr create`, com a descrição padronizada em `.github/pull_request_template.md` (Resumo, Arquivos, Critérios de aceite com checkboxes, Como verificar, Fora de escopo).

**Aceite:**
- [ ] `uv sync` cria o `.venv` com o Python 3.12 (`uv run python --version` mostra 3.12.x); `uv run pytest`, `ruff check` e `ruff format --check` passam.
- [ ] `pre-commit run --all-files` passa, **incluindo o gitleaks**.
- [ ] `make help` lista os alvos setup, ingest, index, serve, eval, eval-gate, test e lint.
- [ ] `docker compose up -d qdrant` sobe e `curl localhost:6333/readyz` responde.
- [ ] `SOURCE.md` tem URL, data, SHA-256 do HTML completo e do PDF e a última REN anotada. O SHA do recorte entra na Fase 1, quando o recorte for gerado. Um teste confere os SHAs dos arquivos que existirem localmente; no CI, só o do recorte, a partir da Fase 1.
- [ ] `uv pip list` mostra o torch com o sufixo `+cpu`, e nenhum pacote `nvidia-*` está instalado.
- [ ] `make smoke` passa localmente com o `gemini-3.8-flash` e o `gemini-3.1-pro-preview` presentes no endpoint, e é pulado no CI.
- [ ] Fluxo: branch `phase-0`, depois push e PR, com o CI verde.

## Fase 1 — Ingestão + parser (HTML)

**Arquivos:**
- `src/aneel_rag/ingest/{html_load.py, segment.py, vigencia.py, parser.py, annotations.py, models.py, report.py, __main__.py}`
- `tests/fixtures/html/*.html`: recortes reais e curtos do `#law-content`
- `tests/unit/test_parser.py`

Pipeline (o desenho final só é fechado depois da inspeção detalhada no início da fase, que vai documentar a marcação no ADR-002):
1. **`extract_law_content` e `html_load`:** o primeiro passo, rodado uma única vez, gera o recorte versionado a partir do HTML completo. Ele isola `#law-content`, remove os `<img>`, `<script>` e o template, e corta o bloco de normas relacionadas e o lixo SQL, com o corte ancorado na assinatura e no fim do último anexo. As figuras viram marcadores `[FIGURA: nome]`. O `html_load` lê **só o recorte**. Há uma asserção de que nenhum unit contém `SELECT `.
2. **`segment`:** percorre os nós em ordem de documento e gera um fluxo de segmentos `{text, kind: plain|struck|bold, anchor}`, tratando `<br><br>` como separador de dispositivo e preservando o texto dos links.
3. **`vigencia`:** classifica cada segmento.
   - `<s>` seguido de uma versão em `<b>` com o mesmo rótulo (§ 2º, IV…) é **superado**: o texto é descartado e contado no relatório.
   - `<s>` seguido de "(Revogado pela …)" vira `status: revoked`. O texto é guardado no unit, mas não entra no índice padrão.
   - `<b>` é vigente. Com "(Redação dada…)" o status é `amended`; sem anotação, `added`.
   - Um artigo inteiro dentro de `<s>`, como o caso do `article157`, é tratado pela mesma regra no nível do artigo.
4. **`parser`:** máquina de estados.
   - Os níveis Título, Capítulo, Seção e Subseção vêm de `span.titulo`, e o Art. vem de `span.artigo`, com o ID normalizado (`article371-A ` vira `art-371-a`).
   - Os §, "Parágrafo único", incisos (`^[IVXLC]+\s*[-–]`) e alíneas (`^[a-z]\)`) saem por regex no início do segmento.
   - IDs: `art-23`, `art-23-p1`, `art-23-pu`, `art-23-inc-II`, `art-23-p1-inc-II-al-a`.
   - Anexos: `annex-I` e afins, com `doc_type: annex`. As tabelas viram texto por linha, e as figuras viram `has_figure: true` com o nome do arquivo.
5. **`annotations`:** extrai `amended_by: [{norma, data}]` a partir das anotações e do `data-original-title` dos links, e `notes: [str]` a partir dos "Vide" e "Suspensos os efeitos". Tudo é removido do texto buscável.
6. **Saídas:**
   - `data/processed/units.jsonl`, com `id`, `hierarchy_path`, `text`, `source_anchor`, `source_url` (se a âncora funcionar), `doc_type: norm|annex`, `status: active|amended|added|revoked`, `amended_by`, `notes` e `has_figure`;
   - `data/processed/manifest.json`, com o SHA-256 do corpus, a data, a versão do parser e as notas do preâmbulo;
   - `data/processed/ingest_report.md`.
7. **Relatório de sanidade conferível contra a fonte**, com cada contagem de saída ao lado da contagem bruta no HTML:

   | Saída do parser | Contagem bruta no HTML |
   |---|---|
   | artigos | spans `span.artigo` (745) |
   | unidades riscadas descartadas | `<s>` (170) |
   | `amended` | ocorrências de "Redação dada" (339 dentro de `<b>`) |
   | `revoked` | "Revogado pela" (12) |

   O relatório também traz:
   - **lacunas e duplicatas** na sequência 1–679 (com sufixos -A), explicadas;
   - a lista de todos os revogados e de todas as notas de vigência;
   - uma amostra de 10 unidades com seed fixa, com o `source_anchor`, para você abrir no navegador.

**Aceite:**
- [ ] Os testes de fixture passam com recortes reais para: artigo simples; artigo com §§ e incisos; dispositivo alterado (`<s>` + `<b>` com "Redação dada", onde só a versão nova sobrevive); dispositivo revogado; artigo inteiro riscado; inclusão em `<b>` sem anotação; artigo com letra (`-A`); nota "Suspensos os efeitos".
- [ ] Nenhum ID duplicado entre os units não revogados.
- [ ] Nenhum texto de `<s>` aparece em units `active`, `amended` ou `added` (teste de propriedade).
- [ ] Nenhum unit contém "SELECT", "Norma revogada" ou "Norma em vigor" (as sobras da lista de normas relacionadas).
- [ ] As contagens do relatório batem com as contagens brutas, ou a diferença vem explicada linha a linha.
- [ ] A ingestão é idempotente: o `units.jsonl` sai byte a byte igual entre duas execuções.

## Fase 2 — Chunking + indexação + retrieval

**Arquivos:**
- `src/aneel_rag/chunking/{structural.py, fixed.py, models.py}`
- `src/aneel_rag/retrieval/{embedder.py, index.py, retriever.py, reranker.py, modes.py, query.py}`
- `tests/unit/{test_chunking.py, test_retriever_inmemory.py}`
- `docs/adr/002-*.md`, `docs/adr/003-*.md`

Componentes:
- **Chunk:** `chunk_id`, `text` (com o prefixo do caminho e do caput), `unit_ids[]`, `article_id`, `doc_type`, `status` e `strategy`.
- **`embedder`:** `BGEM3FlagModel` gera o vetor denso e os pesos léxicos (que viram o vetor esparso). Tem cache em disco por hash do chunk e roda em lote.
- **`index`:** coleção com o vetor denso `dense` (1024, cosseno) e o esparso `sparse`. Cria índices de payload em `status` e `doc_type`.
- **`retriever`:** os modos `dense | sparse | hybrid | hybrid+rerank` vêm da config. Por padrão filtra `status != revoked` e `doc_type == norm`, com flags para incluir anexos e revogados.

**Aceite:**
- [ ] Testes de chunking: todo chunk estrutural tem o caminho e o caput, a união dos `unit_ids` cobre 100% dos units indexáveis, e o chunk fixo respeita o tamanho e o overlap.
- [ ] Um teste do retriever com Qdrant `:memory:` e embedder fake roda os 4 modos e confirma que os filtros padrão excluem revogados e anexos.
- [ ] Localmente, `make index` indexa o corpus no Qdrant do Docker.
- [ ] Smoke test: `python -m aneel_rag.retrieval.query "…" --mode …` funciona nos 4 modos.

## Fase 3 — Grafo LangGraph + validação + abstenção

**Arquivos:**
- `src/aneel_rag/graph/{state.py, nodes.py, build.py, schemas.py, citations.py}`
- `src/aneel_rag/llm/{provider.py, factory.py}`
- `prompts/*.md`
- `tests/unit/{test_validate_citations.py, test_graph_routing.py}`
- `docs/adr/004-*.md`, `docs/adr/006-*.md`

Desenho:
- **Estado:** `TypedDict` com `question`, `trace_id`, `retrieved`, `reranked`, `context_sufficient`, `answer`, `validation`, `attempts` e `final`.
- **Nós:** `retrieve → rerank → grade_context → (generate | abstain)`, depois `generate → validate_citations → (END | generate [1 retry com os erros] | abstain)`.
- **`AnswerSchema`:** `answer`, `citations: [{unit_id, quote}]` e `abstained`. Uma resposta não abstida com `citations` vazia é inválida.
- **Política D6 em `citations.py`:**
  - a quote tem **20 a 300 caracteres**;
  - a quote precisa ser **substring normalizada** do texto do unit citado (NFKC, casefold, espaços colapsados, aspas e travessões unificados);
  - o `unit_id` precisa estar no contexto recuperado;
  - o **unit mais específico** é exigido. Citar o artigo só é preciso quando a quote está no caput. Citar o artigo com uma quote que está num § ou inciso é **aceito, mas marcado `imprecise`**;
  - o resultado é `valid | imprecise | invalid` por citação.
- **`abstain`:** devolve a mensagem padrão e os 3 trechos mais próximos.

**Aceite:**
- [ ] O teste de `validate_citations` cobre: ID inexistente; ID fora do contexto; quote com espaços ou aspas diferentes (válida); quote parafraseada (inválida); quote com menos de 20 ou mais de 300 caracteres (inválida); citação ao artigo com quote do caput (válida); citação ao artigo com quote de § (imprecisa).
- [ ] O teste do grafo usa LLM fake e cobre os 4 caminhos: sucesso; contexto insuficiente que leva a abstain; falha seguida de retry com sucesso; duas falhas que levam a abstain.
- [ ] A troca de provider por config é testada com duas configs.
- [ ] Smoke test local com o `gemini-3.8-flash`: uma pergunta respondível retorna citação válida, e uma pergunta fora do escopo se abstém.

## Fase 4 — Dataset (termina com uma PARADA para você validar)

**Arquivos:** `eval/schema.py`, `eval/dataset.jsonl`, `eval/draft_questions.py`, `eval/validate_dataset.py`, `eval/VALIDATION_GUIDE.md`, `prompts/draft_questions.md` e `tests/unit/test_dataset_schema.py`.

- **Geração:** são **90 candidatas em 3 lotes de 30**. A distribuição total é 30 `factual_single`, 20 `multi_article`, 20 `deadline_or_value` e 20 `unanswerable`, e cada lote é estratificado. A amostragem dos units é por seed e por Título.
- **Status:** todas as candidatas entram com `status: draft` e `validated_by: null`.
- **`unanswerable` como quase-acerto:** cada uma é gerada a partir de um unit real, com um tema da norma e uma pergunta vizinha cuja resposta não está na norma. O `notes` registra o unit de origem e por que a pergunta é irrespondível. O guia de validação traz o critério "nunca absurda".
- **Regra do VALIDATION_GUIDE:** nas perguntas `deadline_or_value`, os `expected_unit_ids` **sempre apontam para o dispositivo no artigo**, nunca para a tabela de prazos depois do Art. 679. O `validate_dataset.py` rejeita IDs `annex-*` nessa categoria.
- **Meta:** pelo menos 50 `validated`. A Fase 5 só avalia com as validadas e avisa se houver menos de 50.

**Aceite:**
- [ ] O script gera um lote de 30 com a distribuição correta, todas como draft. Um teste garante que ele não consegue escrever `validated`.
- [ ] `validate_dataset.py` passa: schema ok, `expected_unit_ids` existentes, IDs únicos, nenhum `validated` sem `validated_by`.
- [ ] **PARADA**: você valida as perguntas antes da Fase 5.

## Fase 5 — Avaliação completa + ablações + eval-gate

**Arquivos:**
- `eval/metrics.py`
- `eval/ragas_metrics.py`: juiz `gemini-3.1-pro-preview` e embeddings bge-m3 locais
- `eval/run_eval.py` e `eval/gate.py`
- `config/ablations/{dense,hybrid,hybrid_rerank,fixed_chunking}.yaml`
- `eval/thresholds.yaml` (vazio, com TODO)
- `tests/unit/test_metrics.py`
- `docs/adr/005-*.md`

Métricas:
- **Principais:** recall@k e MRR **no nível de artigo**.
- **Secundárias:** recall@k e MRR no nível de unit.
- Taxas de citações `valid`, `imprecise` e `invalid`.
- Acurácia de abstenção nas `unanswerable` e taxa de falsa abstenção.
- Faithfulness e answer relevancy (RAGAS).

Relatório:
- Sai em `eval/reports/YYYY-MM-DD_<sha>_<confighash>.{md,json}`.
- Contém: **o SHA-256 do corpus**, o N de validadas usadas e o N de drafts ignoradas, os modelos e as versões das bibliotecas, e a tabela de ablação.

**Cache do juiz:**
- Cada avaliação do juiz é gravada em `data/cache/judge/<sha256>.json`, com a chave sendo o hash de (`question`, `answer`, `contexts`, `judge_model_id`).
- O relatório informa o diretório do cache, quantos acertos e quantas chamadas novas houve, e o hash do manifesto do cache.

**Calibração do juiz:**
- `eval/make_calibration.py` gera `eval/judge_calibration.jsonl` com cerca de 20 respostas reais da config principal. Cada item tem `question`, `answer`, `contexts`, `faithful: null` e `status: draft`.
- Você rotula `faithful: true/false` e marca `validated`, como no dataset.
- O relatório inclui a **concordância juiz × humano** (acurácia e kappa de Cohen) só sobre os itens validados, com o N. Sem itens validados, aparece "TBD".

**Escopo das ablações:** `dense`, `hybrid`, `hybrid+rerank` e `fixed` medem **só retrieval** (recall e MRR determinísticos, sem LLM). O pipeline completo (geração, validação de citações, abstenção) e o **RAGAS com juiz rodam só na config principal**.

Gate: `make eval-gate` falha explicitamente enquanto `thresholds.yaml` estiver vazio.

**Aceite:**
- [ ] Os testes das métricas com valores calculados à mão passam no CI, incluindo a concordância e o kappa.
- [ ] Rodar a avaliação duas vezes seguidas: a segunda faz 0 chamadas novas ao juiz (100% de acerto no cache, mostrado no relatório).
- [ ] `judge_calibration.jsonl` é gerado só com drafts. **PARADA** para você rotular, e depois o relatório mostra a concordância.
- [ ] O primeiro relatório real é gerado e commitado.
- [ ] Você define os limiares, e então o gate fica reproduzível.

## Fase 6 — Observabilidade + API + demo (OPCIONAL, fora do corte de publicação)

**Arquivos:**
- `src/aneel_rag/observability/{tracing.py, logging.py}`: callback do Langfuse **Cloud** quando `LANGFUSE_ENABLED=true`, senão um no-op. Os logs saem em JSON com `trace_id`.
- `src/aneel_rag/api/{app.py, schemas.py}`: `POST /ask` e `GET /health`.
- `app/demo.py`.
- `tests/unit/test_api.py`.

**Aceite:**
- [ ] Com `LANGFUSE_ENABLED=false` não há chamada de rede (teste).
- [ ] Com o Langfuse ligado, um trace com spans por nó aparece no Langfuse Cloud (verificação manual).
- [ ] `make serve` sobe a API, e `curl /ask` devolve a resposta e o `trace_id`.

## Fase 7 — README final

O README cobre:
- o problema;
- a arquitetura, com diagrama Mermaid;
- as decisões, com links para os ADRs;
- como rodar;
- os resultados, só com números de relatório e link para ele;
- as limitações: o leis.org é a plataforma oficial da ANEEL, mas **o texto compilado não substitui a publicação no DOU**; o **snapshot é datado** (data e SHA no `SOURCE.md`); o conteúdo das figuras e fórmulas não está no texto; o parser é heurístico para §, inciso e alínea; o dataset é pequeno; há um juiz LLM;
- o aviso de projeto pessoal;
- a seção "Sobre (PT-BR)".

**Aceite:**
- [ ] O teste `test_readme_numbers.py` olha **só a seção `## Results`** e só **padrões de métrica** (`\d+(\.\d+)?\s*%` e decimais como `0.83`). Ele falha se a linha não tiver link para `eval/reports/`. Números comuns (Art. 679, N=52) não disparam.

## Fase 8 (bônus) — llama.cpp local

Entram `config/providers/local.yaml`, `eval/compare_providers.py` e um relatório comparativo de qualidade, latência (p50 e p95) e custo, todos com o mesmo dataset.

**Aceite:**
- [ ] A suíte roda com `--config config/providers/local.yaml`, e o relatório sai em `eval/reports/`.

---

## Riscos técnicos e mitigação

| Risco | Mitigação |
|---|---|
| Os dispositivos não têm marcação: o texto é plano, separado por `<br><br>` | Segmentar por `<br><br>` e ancorar a regex no início do segmento. Fixtures reais por variante. Teste de propriedade: cada segmento vigente pertence a exatamente um unit. |
| Parear `<s>` superado com o `<b>` substituto errado | Parear pelo rótulo (§ Nº, inciso romano, alínea) dentro do mesmo artigo. O relatório lista os pares e os `<s>` órfãos (estes devem ser só os revogados). |
| `<b>` usado para outras coisas (notas "Vide", destaques) | Classificar pelo conteúdo: um `<b>` que começa com "(Vide" ou "(Suspens" vira nota. O relatório lista todos os `<b>` sem "Redação dada" (cerca de 24) para revisão manual. |
| Fim do texto normativo mal cortado: o lixo de normas relacionadas e o SQL entram | Corte por âncora e asserções de conteúdo proibido nos testes. |
| Ordem de anexos estranha (o texto cita "ANEXO IV" antes do Anexo I) | Detectar o cabeçalho de anexo só depois do Art. 679 e da assinatura. |
| Figuras e fórmulas (28 imagens) sem texto | Flag `has_figure`. Declarar a limitação. O dataset evita perguntas cuja resposta esteja só numa figura. |
| A âncora `#article23` não funcionar no site ao vivo (renderização via JS, `º` na URL) | Verificar na Fase 1. Se falhar, fica só o `source_anchor` e o motivo é documentado. |
| Snapshot manual desatualiza | `SOURCE.md` com data, SHA e última REN. O relatório amarra as métricas ao SHA do corpus. |
| Embedding do bge-m3 em CPU lento | Cache por hash do chunk e lotes. A ablação reaproveita os embeddings. |
| Python 3.14 do sistema | O `.venv` do projeto fica fixado no 3.12 via uv. |
| Saída estruturada do Gemini via endpoint OpenAI-compat | `json_schema` com fallback para `json_mode`, validação Pydantic e retry de parse separado do retry de citação. |
| O juiz em preview (`gemini-3.1-pro-preview`) mudar ou sumir (risco aceito) | ID fixo e sem `-latest`. Cache por `judge_model_id`. Calibração juiz × humano. O ID entra em todo relatório. O smoke test detecta o sumiço do modelo. Trocar o juiz invalida a comparação, e o relatório registra isso. |
| Cota e rate limit do Gemini | Concorrência limitada, backoff e cache por (pergunta, confighash). |
| Instabilidade de API do RAGAS e LangGraph | Versões fixadas no lock e RAGAS isolado num adaptador. |

---

## Decisões resolvidas
D1 Docker instalado · D3 gerador `gemini-3.8-flash` e juiz `gemini-3.1-pro-preview` · D4 a fonte é o leis.org (HTML) · D5 anexos parseados com `doc_type: annex` e fora do retrieval padrão · D6 quote de 20 a 300 caracteres e unit mais específico, com `imprecise` · D7 artigo como métrica principal, unit como secundária, MRR nos dois · D8 90 candidatas em 3 lotes de 30, meta de pelo menos 50 validadas · D9 Langfuse Cloud (free) · D10 PR por fase com gitleaks · D11 execução direta.

D2 `make` via winget, Makefile como única fonte · D10b `gh` instalado por você, PRs abertos por mim com template · D12 só o recorte `ren1000_law_content.html` é versionado · D13 sem página do PDF, com `source_url` se a âncora funcionar.

Ajustes da aprovação: ablações só de retrieval; torch CPU; smoke test de modelos; limitações do README reescritas; regra de `deadline_or_value` no guia; Fase 6 opcional; `test_readme_numbers` restrito.

## Verificação ponta a ponta (depois da Fase 6)

1. `uv sync --all-groups`, depois `make ingest` e conferir `ingest_report.md` (contagens contra o HTML e 10 amostras abertas no navegador).
2. `docker compose up -d qdrant`, depois `make index` e `python -m aneel_rag.retrieval.query "…" --mode hybrid+rerank`.
3. `make serve`, depois `curl -X POST /ask` com uma pergunta respondível (espera citação válida) e outra fora do escopo (espera abstenção).
4. `make eval`, que gera o relatório com o SHA do corpus, e depois `make eval-gate`.
5. O PR da fase fica com o CI verde, sem download de modelos.
