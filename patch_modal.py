import re

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'r') as f:
    content = f.read()

with open('sts_scripts/bot_template.py', 'r') as f:
    template_content = f.read()

appendix = f"""
---

## PART 3: BOILERPLATE TEMPLATE
Below is the master \`bot_template.py\`. Use this exact structure for all new agents.

```python
{template_content}
```
"""

# The GUIDE_MARKDOWN string ends with:
# - Annoyance:** Stay calm. "Understood completely. Sorry for the inconvenience. Have a great day!"
# `;

new_content = content.replace(
    '- **Annoyance:** Stay calm. "Understood completely. Sorry for the inconvenience. Have a great day!"\n`;',
    f'- **Annoyance:** Stay calm. "Understood completely. Sorry for the inconvenience. Have a great day!"\n{appendix}\n`;'
)

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'w') as f:
    f.write(new_content)

print("Modal patched successfully.")
