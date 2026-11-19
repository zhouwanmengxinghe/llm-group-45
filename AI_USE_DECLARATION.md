# AI-use declaration — Group 45

Project: PatchLab, A Test-Driven Autonomous Debugging and Software Repair Agent.
Members: Zhu Wenpu (3036793380), Ma Jinghan (3036791409), Hou Yifu (3036898738).
Member responsibilities: Hou Yifu led the agent core and model integration; Zhu Wenpu led tools and execution environments; Ma Jinghan led data preparation and experiments.

## Tools and assistance

OpenAI Codex assisted with substantial implementation and revision, test and example development, environment troubleshooting, experiment orchestration, result analysis, documentation drafting and English interface translation. The precise backend model version for every development session was not retained and is not asserted here. AI-generated suggestions were iteratively corrected against executable tests, logs and course documents. Passing checks do not establish that every generated change is correct.

DeepSeek's `deepseek-flash` API alias was used by the implemented repair agent during the recorded model experiments and live examples. Those calls are part of the system being evaluated, distinct from development assistance. The immutable provider checkpoint behind the alias was not independently captured; the alias and configuration hashes are reported instead. Scripted demonstration/fault-injection policies are separately labelled and are not attributed to DeepSeek.

The humanizer-zh writing guidance informed wording of the Chinese review draft: concrete statements, fewer stock transitions and no invented evidence. It was not used to evade disclosure or detection. Source: https://github.com/syw2039/humanizer-zh .

## Human decisions and responsibility

The available project conversation shows human direction of the coursework objective, limited single-agent scope, team-work boundaries, UI and portability requirements, experiment sizes, repair budgets, requested diagnostics and final review workflow. The group remains responsible for design decisions, understanding the submitted code, checking experimental claims, approving the report and presenting the system. The member responsibilities above describe ownership of the work; they do not imply that AI-assisted code was independently handwritten.

## Prompt records and omissions

`ai_records/recoverable_project_prompts_en.md` is the user-selected final development prompt record, retained unchanged. Its scope and record limitations are stated in that file. `ai_records/runtime_prompts.json` separately exports the submitted runtime system prompts; example contexts record repair inputs. Complete early conversations and other members' prompt histories were not available, so the development record is partial. Missing wording or timestamps have not been invented. AI replies are not required by the supplied guide.

Provider credentials and private machine paths are excluded or redacted. Actual experimental results, unresolved tasks and limitations are retained. This declaration does not certify team review that has not yet occurred.
