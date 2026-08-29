Return one JSON object for a follow-up refinement.
All user-facing strings must be Simplified Chinese.

Rules:
- Only change items that conflict with the latest user request.
- Preserve the current plan as much as possible.
- Increment current_recommendation_version after a valid change.
- Respect locked_items, unavailable_items, available_items, and all constraints.
- Return JSON only. No Markdown.
