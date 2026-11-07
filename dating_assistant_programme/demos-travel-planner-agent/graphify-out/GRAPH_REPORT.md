# Graph Report - demos-travel-planner-agent  (2026-06-14)

## Corpus Check
- 47 files · ~63,679 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 330 nodes · 538 edges · 28 communities (24 shown, 4 thin omitted)
- Extraction: 75% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 136 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `dc737c44`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `EmotionRagService` - 20 edges
2. `map_transit_route_summary()` - 12 edges
3. `map_geocode_detail()` - 11 edges
4. `split_book_documents()` - 11 edges
5. `create_llm()` - 10 edges
6. `elapsed_ms()` - 10 edges
7. `generate_love_report_from_messages()` - 9 edges
8. `research_activities()` - 8 edges
9. `create_multi_query_retriever()` - 8 edges
10. `build_indexes()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `download_emotion_report()` --calls--> `find_report_file()`  [INFERRED]
  api/emotion_routes.py → emotion/reports/service.py
- `stream_report_markdown_from_messages()` --calls--> `create_llm()`  [INFERRED]
  emotion/reports.py → core/llm.py
- `generate_report_markdown()` --calls--> `create_llm()`  [INFERRED]
  emotion/reports.py → core/llm.py
- `create_multi_query_retriever()` --calls--> `create_llm()`  [INFERRED]
  emotion/retrieval.py → core/llm.py
- `generate_report_markdown()` --calls--> `create_llm()`  [INFERRED]
  emotion/reports/service.py → core/llm.py

## Communities (28 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (37): _activity_search_terms(), ask_preferences(), assemble_date_plan(), _budget_search_terms(), collect_date_details_hitl(), _compact_search_results(), confirm_departure_hitl(), _date_weekday_label() (+29 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (26): _amap_lnglat(), _first_text(), _format_meters(), _format_minutes(), map_geocode(), map_geocode_detail(), map_transit_route_summary(), map_weather_forecast() (+18 more)

### Community 2 - "Community 2"
Cohesion: 0.12
Nodes (10): create_llm(), chat_history(), trim_input_history(), chunk_text(), _chunk_text(), EmotionRagService, stream_report_markdown(), stream_report_markdown_from_messages() (+2 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (13): elapsed_ms(), new_thread_id(), parse_sse_lines(), require_env(), RealApiTest, setUpClass(), RealDateAgentTest, setUpClass() (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (19): book_config_from_path(), book_files(), candidate_book_paths(), BookConfig, chroma_client(), create_embedding_model(), create_multi_query_retriever(), create_vector_store() (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (15): build_emotion_indexes(), download_emotion_report(), create_love_report_from_markdown(), escape_pdf_text(), find_report_file(), format_report_conversation(), generate_love_report_from_messages(), generate_report_markdown() (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.19
Nodes (11): buildEmotionIndexes(), createEmotionThread(), createThread(), fetchHealth(), invokeRun(), parseSse(), postRun(), streamEmotionChat() (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (14): BudgetTermsOutput, DateDetailsOutput, DepartureOutput, DateInputState, DateOutputState, DateState, 约会助手完整状态。保留部分旧字段以兼容现有前端。, 新会话输入保持可空，核心信息通过对话收集。 (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.28
Nodes (12): create_love_report_from_markdown(), escape_pdf_text(), find_report_file(), format_report_conversation(), generate_love_report_from_messages(), generate_report_markdown(), LoveReport, markdown_to_lines() (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.21
Nodes (9): is_noise_chunk(), normalize_extracted_text(), 简单的书籍内容清洗，包括:     1. 删除与书籍内容无关的推广信息     2. 删除中文间的空格     3. 将3个以上的换行替换成\n\n, base_node_metadata(), is_noise_chunk(), normalize_extracted_text(), 针对每一页数据先进行内容清洗，然后利用LangChain提供的splitter完成chunk的切分, split_book_documents() (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.24
Nodes (9): _chunk_node_names(), _config(), get_thread_state(), invoke_run(), _log_timing(), _public_values(), _timed_graph_stream(), extract_interrupt_value() (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.21
Nodes (7): current_date_context(), _extract_date_from_jionlp(), JioNLP parse_time 典型返回：      {         "type": "time_point",         "defini, JioNLP parse_time 典型返回：      {         "type": "time_point",         "definition, resolve_date_text(), _resolve_date_with_jionlp(), DateParserTest

### Community 12 - "Community 12"
Cohesion: 0.29
Nodes (8): _is_origin_followup_prompt(), _print_final_agenda(), Deployed test script — runs against a live LangSmith Deployment. ==============, run(), print_final_state(), 本地测试脚本。  使用内存 checkpointer 直接运行约会助手图，便于在不启动 FastAPI 的情况下 检查 streaming、interrupt, run(), stream_until_interrupt()

## Knowledge Gaps
- **28 isolated node(s):** `Deployed test script — runs against a live LangSmith Deployment. ==============`, `本地测试脚本。  使用内存 checkpointer 直接运行约会助手图，便于在不启动 FastAPI 的情况下 检查 streaming、interrupt`, `高德地理编码接口典型原始返回：      {         "status": "1",         "info": "OK",`, `高德天气预报接口典型原始返回：      {         "status": "1",         "info": "OK",`, `高德公交路径规划接口典型原始返回：      {         "status": "1",         "info": "OK",` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `map_geocode_detail()` connect `Community 1` to `Community 3`?**
  _High betweenness centrality (0.332) - this node is a cross-community bridge._
- **Why does `_date_area_fields()` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `EmotionRagService` (e.g. with `FakeHistory` and `EmotionRagServiceTest`) actually correct?**
  _`EmotionRagService` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `map_transit_route_summary()` (e.g. with `summarize_transport_options()` and `.test_transit_summary_contains_lines_and_duration_only()`) actually correct?**
  _`map_transit_route_summary()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `map_geocode_detail()` (e.g. with `_date_area_fields()` and `_resolve_departure_with_map()`) actually correct?**
  _`map_geocode_detail()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `split_book_documents()` (e.g. with `build_books_vector_store()` and `.test_cleaned_text_is_split_and_metadata_is_preserved()`) actually correct?**
  _`split_book_documents()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `create_llm()` (e.g. with `stream_report_markdown_from_messages()` and `generate_report_markdown()`) actually correct?**
  _`create_llm()` has 9 INFERRED edges - model-reasoned connections that need verification._