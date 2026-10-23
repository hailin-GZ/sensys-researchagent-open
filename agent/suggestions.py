"""Short contextual user messages, separate from long research/experiment plans."""
from . import schemas
SCHEMA={'type':'array','items':{'type':'string','maxLength':80},'minItems':2,'maxItems':3}
PROMPT=' Return 2–3 followup_questions in English, each a short message the USER can send, roughly 15–40 characters and at most 80. Derive them from this actual topic and remaining decision gaps, not fixed button labels. Suggest useful public desk research, comparisons, explanation or experiment-plan design; do not promise execution in unconnected product accounts, real interviews or private customer systems. Do not ask the user for permission (no Would you like me to), and do not paste long next_steps paragraphs.'

def save(root,values):
    from .confidentiality import clean_text
    from .tools import r
    questions=[]
    for text in values if isinstance(values,list) else []:
        if not isinstance(text,str) or not 1<=len(text.strip())<=80:continue
        text=clean_text(text.strip())
        if text and text not in questions:questions.append(text)
    if questions:r.write_json(root/'suggestions.json',questions[:3])
    return questions[:3]
