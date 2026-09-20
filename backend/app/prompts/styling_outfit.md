Return one JSON object for POST /api/refine-outfit.
All user-facing strings must be Simplified Chinese.

Required shape:
{
  "overall_summary": "string",
  "occasion_assessment": "string",
  "score": {
    "total": 0,
    "verdict": "string",
    "dimensions": [
      {"key": "color", "label": "色彩和谐", "score": 0, "summary": "string"},
      {"key": "proportion", "label": "版型比例", "score": 0, "summary": "string"},
      {"key": "personal_fit", "label": "本人适配", "score": 0, "summary": "string"},
      {"key": "occasion_fit", "label": "场合得体", "score": 0, "summary": "string"},
      {"key": "style_completion", "label": "风格完成度", "score": 0, "summary": "string"}
    ]
  },
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
      "image_instruction": "string"
    }
  ]
}

Rules:
- Diagnose first, then propose interventions.
- Score each of the five dimensions from 0 to 20; total must equal their sum and stay within 0-100.
- Scores evaluate the visible outfit only. Never score the person's body, face, skin tone, attractiveness, identity, or worth.
- Use occasion and change_intensity from current_user_request. For formal occasions, explicitly assess appropriateness and coverage.
- If vision shows a fitted top or visible waistline, do not call it loose or say the waistline is absent.
- When the existing outfit is coordinated, phrase issues as light optimization opportunities.
- Return exactly 3 plans: recommended, minimal, expressive.
- Make the three plans meaningfully different. Do not produce paraphrases of the same change.
- Every plan must name concrete visual attributes instead of vague phrases such as "更有线条感" or "更协调".
- When changing a top, specify its exact color and at least one construction detail: neckline (such as V领/方领/圆领), sleeve, fit, length, fabric, or hem treatment.
- When changing a bottom, specify its exact color and at least one construction detail: rise, silhouette, length, fabric, or hem shape.
- If color is retained, explicitly say "保留原色". If color changes, name the target color; never say only "提亮" or "换个颜色".
- recommended must include at least one clearly visible garment cut, proportion, neckline, layering, or color improvement. Adding an accessory alone is not a valid recommended plan.
- minimal should remain easy to execute but must still describe the exact styling operation and its visible result.
- expressive should include a deliberate color or silhouette direction while preserving the person's identity and most of the original look.
- recommended: replace at most 1 core item, add at most 1 accessory.
- minimal: add 0 accessories, replace at most 1 core item.
- expressive: replace at most 2 core items, add at most 1 accessory.
- Respect locked_items and unavailable_items.
- Set after_image equal to before_image. Do not call image generation.
- Keep output concise: strengths max 2, main_issues max 2, changes 1-2 per plan, each reason under 60 Chinese characters.
- Do not include extra fields, explanations, notes, Markdown, or repeated constraint text.
- Return JSON only. No Markdown.
