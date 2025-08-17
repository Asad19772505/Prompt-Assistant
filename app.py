import json
import re
import streamlit as st

# ---------------------------
# Framework templates
# ---------------------------
FRAMEWORKS = {
    "CO-STAR": ["Context", "Objective", "Style", "Tone", "Audience", "Response"],
    "CRISPE": ["Capacity/Constraints", "Role", "Insight/Context", "Steps", "Persona", "Evaluation"],
    "CLEAR": ["Context", "Language", "Examples", "Analysis/Thinking Style", "Restrictions"],
    "Basic (Context-Objective-Constraints-Examples-Output)": ["Context", "Objective", "Constraints", "Examples", "Output Format"]
}

DEFAULTS = {
    "Style": "Professional, concise, structured",
    "Tone": "Neutral, informative",
    "Audience": "General professional reader",
    "Response": "Provide structured, clear, and actionable answers",
    "Role": "Expert AI assistant",
    "Steps": "Explain step-by-step only when necessary; summarize reasoning (no chain-of-thought).",
    "Evaluation": "Check completeness, clarity, constraint compliance, and coherence before finalizing.",
    "Language": "English",
    "Analysis/Thinking Style": "Structured, evidence-based; brief rationale only.",
}

# ---------------------------
# Prompt generation
# ---------------------------
def generate_prompt(framework: str, inputs: dict) -> str:
    parts = []
    for field in FRAMEWORKS[framework]:
        val = (inputs.get(field) or "").strip()
        if not val:
            val = "Not specified"
        parts.append(f"**{field}:** {val}")
    return "\n\n".join(parts)

# ---------------------------
# Scoring & Rubric
# ---------------------------
RUBRIC_WEIGHTS = {
    # Coverage
    "objective_present": 1.5,
    "context_present": 1.0,
    "constraints_present": 1.0,
    "examples_present": 0.8,
    "output_format_present": 0.7,
    # Quality heuristics
    "objective_quality": 1.2,   # length / specificity
    "constraints_quality": 1.0, # includes style/limits/guardrails
    "examples_quality": 0.8,    # has Input/Output pattern or few-shot cues
    "format_quality": 0.8,      # JSON keys / sectioning cues
    "ambiguity_low": 1.0,       # few vague words, fewer TBDs
}

def _len_tokens(text: str) -> int:
    if not text: return 0
    # very rough token proxy (whitespace + punctuation split)
    return len(re.findall(r"\w+|\S", text))

def _has_any(text: str, keywords: list) -> bool:
    if not text: return False
    t = text.lower()
    return any(k.lower() in t for k in keywords)

def _count_any(text: str, keywords: list) -> int:
    if not text: return 0
    t = text.lower()
    return sum(t.count(k.lower()) for k in keywords)

def score_inputs(inputs: dict) -> dict:
    """Return detailed scoring and suggestions."""
    ctx = (inputs.get("Context") or inputs.get("Insight/Context") or "").strip()
    obj = (inputs.get("Objective") or "").strip()
    cons = (inputs.get("Constraints") or inputs.get("Capacity/Constraints") or inputs.get("Restrictions") or "").strip()
    ex  = (inputs.get("Examples") or "").strip()
    fmt = (inputs.get("Output Format") or "").strip()

    # Coverage checks
    checks = {
        "objective_present": bool(obj),
        "context_present": bool(ctx),
        "constraints_present": bool(cons),
        "examples_present": bool(ex),
        "output_format_present": bool(fmt),
    }

    # Quality checks (heuristics)
    # Objective quality: length and presence of action verbs
    obj_len = _len_tokens(obj)
    action_verbs = ["analyze", "summarize", "compare", "design", "draft", "generate", "evaluate", "classify", "extract"]
    checks["objective_quality"] = (obj_len >= 8) and _has_any(obj, action_verbs)

    # Constraints quality: style/length/guardrails detectable
    guardrail_terms = ["cite", "do not", "avoid", "limit", "word", "tone", "comply", "policy", "no chain-of-thought", "refuse"]
    checks["constraints_quality"] = _has_any(cons, guardrail_terms) or ( _len_tokens(cons) >= 6 )

    # Examples quality: few-shot structure indicators
    example_markers = ["input:", "output:", "example", "shot", "context → response", "instruction:", "response:"]
    checks["examples_quality"] = _has_any(ex, example_markers) or (_count_any(ex, [":"]) >= 2 and _len_tokens(ex) >= 12)

    # Output format quality: json keys or headings
    json_markers = ["{", "}", "json", "keys", "schema"]
    section_markers = ["bullet", "markdown", "sections", "executive summary", "findings", "recommendations"]
    checks["format_quality"] = _has_any(fmt, json_markers + section_markers)

    # Ambiguity penalty (we invert it to a positive check)
    vague_terms = ["tbd", "etc.", "and so on", "something like", "roughly", "maybe", "as needed"]
    high_ambiguity = _has_any(obj + " " + ctx, vague_terms)
    checks["ambiguity_low"] = not high_ambiguity

    # Score aggregation
    max_score = sum(RUBRIC_WEIGHTS.values())
    raw = sum(RUBRIC_WEIGHTS[k] for k, v in checks.items() if v)
    score_10 = round(10 * raw / max_score, 1)

    # Suggestions
    suggestions = []
    if not checks["objective_present"]:
        suggestions.append("Add a clear objective starting with a strong verb (e.g., *Analyze*, *Summarize*, *Design*).")
    elif not checks["objective_quality"]:
        suggestions.append("Make the objective more specific (scope, data, success criteria).")

    if not checks["context_present"]:
        suggestions.append("Provide domain, audience, and key background constraints in **Context**.")
    if not checks["constraints_present"]:
        suggestions.append("Add **Constraints** (tone, word/section limits, must/avoid, compliance/guardrails).")
    elif not checks["constraints_quality"]:
        suggestions.append("Tighten **Constraints**: include style (e.g., *professional*), limits (e.g., *≤200 words*), and guardrails (*no chain-of-thought*, *cite sources*).")

    if not checks["examples_present"]:
        suggestions.append("Add 1–2 **few-shot Examples** (clear *Input → Output* pairs).")
    elif not checks["examples_quality"]:
        suggestions.append("Improve examples: label **Input:** and **Output:** and show the ideal structure.")

    if not checks["output_format_present"]:
        suggestions.append("Specify an **Output Format** (e.g., bullet points or JSON with required keys).")
    elif not checks["format_quality"]:
        suggestions.append("Refine format: define JSON keys or markdown sections (Executive Summary, Findings, Recommendations).")

    if not checks["ambiguity_low"]:
        suggestions.append("Remove vague phrases (e.g., *TBD, etc.*) and state exact scope/assumptions.")

    return {
        "score_out_of_10": score_10,
        "checks": checks,
        "suggestions": suggestions
    }

# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="AI Prompt Generator + Auditor", layout="wide")
st.title("🧠 AI Prompt Generator")
st.subheader("Create Expert-Level Prompts Using Best-Practice Frameworks — now with a quality score.")

framework = st.selectbox("Choose Prompt Framework", list(FRAMEWORKS.keys()))

with st.form("prompt_form"):
    st.write("### 🎯 Core Components")

    # Required fields
    objective = st.text_area(
        "PRIMARY OBJECTIVE* (What should the AI accomplish?):",
        placeholder="Summarize the text...",
        height=100
    )

    context = st.text_area(
        "CONTEXT (Background information, domain, audience):",
        placeholder="Domain: Healthcare, Audience: Medical students...",
        height=100
    )

    # Optional fields
    with st.expander("⚙️ Advanced Settings (Optional)", expanded=False):
        constraints = st.text_area(
            "CONSTRAINTS (Rules, limitations, style, guardrails):",
            placeholder="≤200 words, professional tone, cite sources if used, no chain-of-thought, refuse unsafe tasks...",
            height=100
        )
        examples = st.text_area(
            "EXAMPLES (Few-shot Input → Output samples):",
            placeholder="Example 1\nInput: [Text]\nOutput: [Ideal response]\n\nExample 2\nInput: ...\nOutput: ...",
            height=120
        )
        output_format = st.text_input(
            "OUTPUT FORMAT (Structure, JSON, markdown, etc.):",
            placeholder="JSON with keys: summary, key_points[], recommendations[]"
        )

    submitted = st.form_submit_button("✨ Generate Standardized Prompt")

if submitted:
    if not objective:
        st.error("Please provide at least a Primary Objective")
    else:
        # Collect inputs (plus defaults to support all frameworks)
        inputs = {
            # Basic
            "Context": context,
            "Objective": objective,
            "Constraints": constraints,
            "Examples": examples,
            "Output Format": output_format,
            # CO-STAR
            "Style": DEFAULTS["Style"],
            "Tone": DEFAULTS["Tone"],
            "Audience": DEFAULTS["Audience"],
            "Response": DEFAULTS["Response"],
            # CRISPE
            "Capacity/Constraints": constraints or "Follow constraints and platform policies.",
            "Role": DEFAULTS["Role"],
            "Insight/Context": context,
            "Steps": DEFAULTS["Steps"],
            "Persona": "Helpful, professional assistant",
            "Evaluation": DEFAULTS["Evaluation"],
            # CLEAR
            "Language": DEFAULTS["Language"],
            "Analysis/Thinking Style": DEFAULTS["Analysis/Thinking Style"],
            "Restrictions": constraints or "No chain-of-thought; cite sources if used; comply with safety policies.",
        }

        # Build prompt and score it
        prompt = generate_prompt(framework, inputs)
        audit = score_inputs(inputs)

        # Output
        st.success("✅ Generated Professional Prompt:")
        st.code(prompt, language="markdown")

        # Scoring UI
        st.subheader("🔎 Prompt Quality")
        score = audit["score_out_of_10"]
        st.metric("Prompt Quality (0–10)", score)
        st.progress(min(1.0, score / 10.0))

        cols = st.columns(2)
        with cols[0]:
            st.write("**Checks**")
            checks_pretty = {k: ("✅" if v else "❌") for k, v in audit["checks"].items()}
            st.json(checks_pretty)
        with cols[1]:
            st.write("**Suggestions to Improve**")
            if audit["suggestions"]:
                for s in audit["suggestions"]:
                    st.write(f"- {s}")
            else:
                st.write("Looks great! Consider adding more specific success criteria if needed.")

        # Downloads
        st.subheader("⬇️ Export")
        st.download_button("Download Prompt (.txt)", data=prompt, file_name="prompt.txt", use_container_width=True)
        payload = {"framework": framework, "inputs": inputs, "prompt": prompt, "score": score}
        st.download_button("Download Audit (.json)", data=json.dumps(payload, indent=2), file_name="prompt_audit.json", use_container_width=True)

# Sidebar usage
st.sidebar.header("How To Use")
st.sidebar.markdown("""
1) Pick a **framework** (CO-STAR / CRISPE / CLEAR / Basic).  
2) Fill **Objective** and **Context** (required).  
3) Optionally add **Constraints**, **Examples**, and **Output Format**.  
4) Click **Generate** to get your prompt and a **quality score** with suggestions.  
5) Export TXT/JSON for reuse.
""")

st.sidebar.markdown("### Rubric Dimensions")
st.sidebar.markdown("""
- **Coverage**: Objective, Context, Constraints, Examples, Output Format  
- **Quality**: Specific objective, enforceable constraints/guardrails, example structure, explicit output format  
- **Clarity**: Low ambiguity (avoid *TBD, etc.*)
""")
