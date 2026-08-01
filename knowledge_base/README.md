# Knowledge Base for Habit Tracker AI Planner

This folder contains reference materials for building a RAG (Retrieval-Augmented Generation) system to improve the AI evening planner in the Habit Tracker app.

## About Andrew Huberman's "Protocols" Book

The primary target for this knowledge base was **"Protocols: An Operating Manual for the Human Body"** by Andrew D. Huberman, Ph.D. (2025).

- **Book on Amazon**: https://www.amazon.com/s?k=Dr.+Andrew+Huberman+Protocols
- **Status**: The book is a paid publication and no legal free PDF download was found online. The book is available in hardcover, Kindle, and audiobook formats.
- **Alternative**: Instead of the book PDF, this knowledge base uses Huberman's freely published podcast notes and toolkits from hubermanlab.com, which cover the same protocols described in the book.

## Folder Structure

### `/huberman_toolkits/`
Official Huberman Lab toolkit notes in English. These are the most directly applicable to the app's AI planner:
- `01_sleep_toolkit.md` — Comprehensive sleep optimization protocols (Episode 84)
- `02_focus_toolkit.md` — Focus and concentration tools (Episode 88)

### `/circadian_rhythm_research/`
Scientific research on circadian rhythm, exercise timing, and sleep:
- `01_exercise_timing_and_circadian_rhythm.md` — How exercise at different times of day affects sleep, with specific recommendations for the app

### `/chinese_summaries/`
Chinese-language summaries of the above resources, for bilingual reference:
- `01_时序抗衰老与昼夜节律.md` — Chronogeroprotection and circadian rhythm intervention strategies
- `02_Sleep_Toolkit中文总结.md` — Chinese summary of Sleep Toolkit
- `03_Focus_Toolkit中文总结.md` — Chinese summary of Focus Toolkit

## How This Applies to the App

The AI planner's job is to schedule remaining habits before bedtime. The knowledge base informs these decisions:

1. **Habit timing rules**: When each type of habit is biologically appropriate
2. **Sleep protection**: Which activities to skip close to bedtime (e.g., intense exercise within 2-3h of sleep)
3. **Energy curves**: Cortisol peaks in morning, serotonin in afternoon, melatonin in evening
4. **Body temperature**: The key variable for sleep onset — exercise raises temp, which must drop for sleep
5. **Ultradian rhythms**: 90-minute cycles for focused work
6. **Recovery tools**: NSDR, meditation, and other low-energy evening alternatives

## Key Rules for the AI Planner (Extracted)

| Activity | Latest Time Before Bed | Reason |
|----------|----------------------|--------|
| Intense exercise | 2-3 hours | Raises core body temperature, cortisol, adrenaline |
| Heavy meal | 3 hours | Disrupts sleep, metabolism still active |
| Caffeine | 8-10 hours | Half-life 5-6 hours |
| Intense mental work | 2 hours | Raises body temp, sympathetic activation |
| Bright screen light | 1-2 hours | Suppresses melatonin |
| Alcohol | Avoid entirely | Destroys sleep architecture |

| Activity | Good Evening Alternative? |
|----------|--------------------------|
| Stretching / Yoga | Yes — promotes relaxation |
| Walking | Yes — gentle movement |
| Reading (physical book, dim light) | Yes — winds down brain |
| Meditation | Yes — parasympathetic activation |
| Journaling | Yes — cognitive offloading |
| NSDR | Yes — deep rest, restores dopamine |

## Suggested RAG Implementation

For your future RAG build:

1. **Chunking**: Each `.md` file can be split by `##` headers into meaningful chunks
2. **Embeddings**: Use a multilingual embedding model (e.g., text-embedding-3-small) since content is mixed EN/ZH
3. **Vector store**: ChromaDB or FAISS work well for this size (~6 documents)
4. **Query strategy**: When user clicks "What to do now", retrieve relevant chunks based on:
   - Current time
   - Bedtime
   - List of uncompleted habits (with their phases)
5. **Prompt augmentation**: Inject retrieved knowledge into the existing system prompt in `ai_planner.py`

## Sources

All content was gathered from publicly available sources:
- Huberman Lab official website: https://www.hubermanlab.com/
- Feishu document summaries (Chinese): links in each file
- Toutiao health articles: links in each file
- Academic journals referenced within Huberman's episode notes

No copyrighted material was reproduced. All notes are summaries and paraphrases.
