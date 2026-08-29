Return one JSON object for POST /api/refine-outfit.
All user-facing strings must be Simplified Chinese.

Required shape:
{
  "overall_summary": "string",
  "strengths": ["string"],
  "main_issues": ["string"],
  "keep_items": ["string"],
  "diagnosis_dimensions": [
    {"dimension": "color|proportion|silhouette|style_consistency|occasion_fit|visual_focus", "status": "good|warning|issue", "summary": "string"}
  ],
  "plans": [
    {
      "plan_id": "string",
      "plan_type": "recommended|minimal|expressive",
      "title": "string",
      "summary": "string",
      "change_budget": "string",
      "changes": [{"target": "string", "action": "string", "from": "string", "to": "string", "reason": "string"}],
      "before_image": "string",
      "after_image": "string",
      "image_instruction": "string",
      "constraint_check": {"passed": true, "notes": ["string"]}
    }
  ]
}

Rules:
- Diagnose first, then propose interventions.
- If vision shows a fitted top or visible waistline, do not call it loose or say the waistline is absent.
- When the existing outfit is coordinated, phrase issues as light optimization opportunities.
- Return exactly 3 plans: recommended, minimal, expressive.
- recommended: replace at most 1 core item, add at most 1 accessory.
- minimal: add 0 accessories, replace at most 1 core item.
- expressive: replace at most 2 core items, add at most 1 accessory.
- Respect locked_items and unavailable_items.
- Use placeholder after_image values. Do not call image generation.
- Return JSON only. No Markdown.
