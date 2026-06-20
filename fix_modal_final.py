import re

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'r') as f:
    content = f.read()

# Read the bot template again
with open('sts_scripts/bot_template.py', 'r') as f:
    template_content = f.read()

# We need to construct the entire GUIDE_MARKDOWN string cleanly.
# The original template content might contain ` and $. We must escape them
# so it sits cleanly inside `...` in javascript.

escaped_template = template_content.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')

# The block to replace is everything from:
# ## PART 3: BOILERPLATE TEMPLATE
# ... up to
# `;

start_idx = content.find("## PART 3: BOILERPLATE TEMPLATE")
end_idx = content.find("`;", start_idx)

if start_idx != -1 and end_idx != -1:
    new_appendix = f"## PART 3: BOILERPLATE TEMPLATE\nBelow is the master \\`bot_template.py\\`. Use this exact structure for all new agents.\n\n\\`\\`\\`python\n{escaped_template}\n\\`\\`\\`\n"
    content = content[:start_idx] + new_appendix + content[end_idx:]
    with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'w') as f:
        f.write(content)
    print("Fixed JS markdown string.")
else:
    print("Could not find PART 3 string.")

