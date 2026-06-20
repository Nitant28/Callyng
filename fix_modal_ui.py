import re

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'r') as f:
    content = f.read()

# I need to escape template_content properly for a template literal.
# Using template_content.replace('`', '\\`').replace('$', '\\$')
with open('sts_scripts/bot_template.py', 'r') as f:
    template_content = f.read()

# Find the section to replace: from <h4 className="text-xl font-bold ... 5. Boilerplate Template to the end of the section </section>
pattern = r'<section>\s*<h4 className="text-xl font-bold[^>]*>\s*5\. Boilerplate Template.*?</section>'
match = re.search(pattern, content, re.DOTALL)

if match:
    # Use backticks to inject the raw string
    safe_content = template_content.replace('`', '\\`').replace('$', '\\$')
    
    fixed_section = f"""<section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  5. Boilerplate Template
                </h4>
                <p className="mb-4 text-sm text-on-surface-variant dark:text-molten-text-muted">
                  Below is the master <code>bot_template.py</code>. Use this exact structure for all new agents.
                </p>
                <div className="bg-black/50 p-4 rounded-lg border border-outline-variant/30 max-h-[600px] overflow-y-auto">
                  <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap">
                    {{`{safe_content}`}}
                  </pre>
                </div>
              </section>"""
              
    content = content[:match.start()] + fixed_section + content[match.end():]
    with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'w') as f:
        f.write(content)
    print("Fixed.")
else:
    print("Pattern not found!")
