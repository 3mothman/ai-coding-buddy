"""Explicit, optional real-model scenario check. Never run by the app automatically."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from buddy.analysis import Snapshot
from buddy.gemini_analysis import GeminiTutor, DEFAULT_FLASH
from buddy.runtime_checks import verify_offline_runtime

REFERENCE = """#include <stdio.h>
int main(void) {
    int a[] = {4, -2, 9, 3};
    int greatest = a[0];
    for (int i=1; i<4; i++) {
        if (a[i]>greatest) greatest=a[i];
    }
    printf("%d", greatest);
    return 0;
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live-analysis", action="store_true", help="Consent to send built-in sample C exercises to Google; API usage may be charged.")
    parser.add_argument("--model", default=DEFAULT_FLASH)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    verify_offline_runtime()
    report = {"offline_runtime": "passed", "live_model": args.model,
              "live_analysis": "not run", "microphone_and_voice_quality": "requires manual in-app check"}
    if args.run_live_analysis:
        if not os.getenv("GEMINI_API_KEY"):
            raise SystemExit("Set GEMINI_API_KEY locally first. Do not paste it into chat or commit it.")
        tutor = GeminiTutor(args.model)
        snap = Snapshot("Find and print the greatest integer in an array.", REFERENCE, "", reason="prepare")
        prepared = tutor.analyze(snap)
        understanding = prepared.structured["reference"]
        cases = {
            "array_progress": "#include <stdio.h>\nint main(void) {\n int a[]={4,-2,9,3};\n}",
            "wrong_bound": "#include <stdio.h>\nint main(void) { int a[]={4,-2,9,3}; int greatest=a[0];\n for(int i=1; i<=4; i++) { if(a[i]>greatest) greatest=a[i]; }\n printf(\"%d\",greatest); }",
            "while_alternative": "#include <stdio.h>\nint main(void) { int a[]={4,-2,9,3}; int greatest=a[0]; int i=1;\n while(i<4) { if(a[i]>greatest) greatest=a[i]; i++; }\n printf(\"%d\",greatest); return 0; }",
        }
        results = {}
        for name, code in cases.items():
            response = tutor.analyze(replace(snap, code=code, reason="check", reference_analysis=understanding))
            record = response.structured
            results[name] = {"message": response.message, "action": response.action,
                             "issue": record["analysis"]["issue"], "confidence": record["analysis"]["confidence"],
                             "completed": record["student_progress"]["completed"]}
        # These are observations for human evaluation, not an automatic correctness claim.
        report["live_analysis"] = "responses received; review observations"
        report["observations"] = results
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
