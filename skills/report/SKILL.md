# Marketing report skill v1

1. Read the data contract. Never invent fields, channel names, dates, spend or ROI.
2. Query the required metrics through query_metrics. The server computes rates.
3. For research, compare groups, inspect sample sizes, test hypotheses and register claims with evidence IDs.
4. Call draft_report with a title, safe intro_html and bar/line/table recipe. Use only allowed metrics.
5. Cite recorded claim IDs. Report numbers come from browser-time retrieval of evidence, never copied into HTML.
6. Call finish with the exact goal criteria covered. Only the human can publish.

Allowed intro HTML: p, h2, h3, strong, em, ul, ol, li, br without attributes.
No scripts, links, images, CSS, event handlers or network URLs.
Month is a categorical month in the sample, not a complete daily timeline.
Revenue means a purchase boolean. Observational differences are not causal effects.
If necessary information is absent, ask_user with a concrete question.
