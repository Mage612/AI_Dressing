Return one JSON object for POST /api/recommend-item.
All user-facing strings must be Simplified Chinese.

Required shape:
{
  "recommendations": [
    {
      "plan_id": "string",
      "strategy": "safe|recommended|expressive",
      "strategy_label": "string",
      "title": "string",
      "occasion_summary": "string",
      "tags": ["string"],
      "items": [{"type": "string", "description": "string"}],
      "reason": "string",
      "image_url": "string",
      "image_instruction": "string",
      "constraint_check": {"passed": true, "notes": ["string"]}
    }
  ]
}

Rules:
- Return exactly 3 recommendations: safe, recommended, expressive.
- Keep the uploaded fixed item. Do not replace it.
- Respect unavailable_items and explicit negative constraints.
- If available_items says the user only has short tops, every plan should use a short top or explain a no-new-purchase equivalent.
- If the user says no high heels, footwear must be flat shoes, sneakers, loafers, Mary Janes without heel, or similar low/no-heel options.
- Make the three plans meaningfully different in at least two dimensions.
- Use placeholder image_url values. Do not call image generation.
- Return JSON only. No Markdown.
