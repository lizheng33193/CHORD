"""Plan 07 Phase 0 Task 0.3 — baseline token statistics on 5 sample NL queries."""
from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.prompt_assembler import assemble_prompt
from data_acquisition_agent.schemas import GenerateRequest, TargetCountry

SAMPLES = [
    "查找最近 7 天活跃用户的 top 10",
    "统计本月有逾期记录的用户数量",
    "导出 30 天内首贷通过且 mob1 无逾期的用户清单",
    "对比上周和本周的 eKYC 拦截率",
    "构建一张近 90 天复借首贷客群的标签宽表",
]


def main() -> None:
    manifest = load_manifest("mexico")
    if manifest.analyst_private_prefix != "dm_model.yyp_tmp_":
        raise SystemExit("non-prod prefix detected, refuse to run")

    totals: list[int] = []
    for idx, query in enumerate(SAMPLES, 1):
        req = GenerateRequest(
            natural_language_request=query,
            target_country=TargetCountry.MEXICO,
        )
        _prompt, tokens, _files, _hits = assemble_prompt(req, manifest)
        totals.append(tokens)
        print(f"[{idx}] prompt_tokens={tokens} query={query}")

    avg = sum(totals) // len(totals)
    print(f"BASELINE_AVG_PROMPT_TOKENS={avg}")


if __name__ == "__main__":
    main()
