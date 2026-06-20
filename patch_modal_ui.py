import re

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'r') as f:
    content = f.read()

with open('sts_scripts/bot_template.py', 'r') as f:
    template_content = f.read()

ui_appendix = f"""
              <section>
                <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
                  5. Boilerplate Template
                </h4>
                <p className="mb-4 text-sm text-on-surface-variant dark:text-molten-text-muted">
                  Below is the master <code>bot_template.py</code>. Use this exact structure for all new agents.
                </p>
                <div className="bg-black/50 p-4 rounded-lg border border-outline-variant/30 max-h-[600px] overflow-y-auto">
                  <pre className="text-xs font-mono text-green-400 whitespace-pre-wrap">
{repr(template_content)[1:-1].replace('<', '&lt;').replace('>', '&gt;')}
                  </pre>
                </div>
              </section>
"""

# Append inside the 'technical' tab before its closing </div>
new_content = content.replace(
    '</section>\n\n            </div>\n          )}\n\n          {activeTab === \'conversational\'',
    '</section>\n' + ui_appendix + '\n            </div>\n          )}\n\n          {activeTab === \'conversational\''
)

with open('frontend/src/components/shared/ScriptingGuideModal.jsx', 'w') as f:
    f.write(new_content)

print("Modal UI patched successfully.")
