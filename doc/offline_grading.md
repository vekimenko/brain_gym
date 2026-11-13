# Offline Grading

Assuming for each question I have an 'ideal answer'. Is it possible to use any NLP techniques I can run purely locally without using LLM to evaluate how my answer is close to the ideal answer? Does using embedding help in this?

Yes. You can run a fully local, non-LLM evaluator that compares your spoken/typed answer with a prewritten “ideal answer,” and **embeddings are the most useful single technique** for it. They measure whether you expressed the same ideas in different words, rather than merely matching exact words. [sbert](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)

## What embeddings do well

Encode both the ideal answer and your response with a local sentence-embedding model, then compute cosine similarity. Sentence Transformers is designed for exactly this semantic-textual-similarity use case, and its similarity function defaults to cosine similarity. [sbert](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)

For your app, this would replace or supplement the current LLM call in `grade_answer()`:

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def semantic_similarity(ideal: str, user_answer: str) -> float:
    embeddings = model.encode([ideal, user_answer], normalize_embeddings=True)
    return float(util.cos_sim(embeddings[0], embeddings [sbert](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)))
```

`all-MiniLM-L6-v2` is small, fast, and runs offline; Sentence Transformers represents each text as a fixed-size vector and computes similarity very quickly. [sbert](https://www.sbert.net/docs/sentence_transformer/usage/usage.html)

A score near 1.0 means the two texts are semantically close; a lower score means less overlap in meaning. But it is a **similarity score, not a judgement of factual correctness**.

## What embeddings miss

| Dimension | Embedding similarity | Better technique |
|---|---|---|
| Paraphrasing | Strong | Sentence embeddings |
| Synonyms / wording differences | Strong | Sentence embeddings |
| Missing a required point | Partial | Key-point coverage |
| Adding irrelevant material | Weak | Key-point coverage / entailment |
| Contradicting the ideal answer | Weak | NLI / entailment model |
| Logical order or explanation quality | Weak | Structural heuristics, or an LLM |
| Exact facts, names, numbers | Moderate | Keyword/entity matching |

The main limitation is that embeddings compress an entire answer into one vector. They cannot reliably tell you *which* required point you omitted, whether you made a factual error, or whether your reasoning followed correctly. SpaCy similarly notes that document similarity based on averaged vectors is insensitive to word order and may not capture fine-grained distinctions. [sbert](https://www.sbert.net/docs/quickstart.html)

## Best local approach

Use a **hybrid score**, not embedding similarity alone:

1. **Semantic similarity**: cosine similarity between the ideal answer and user answer.
2. **Required-point coverage**: split the ideal answer into 3–8 atomic claims, then compare each claim with the user answer; report which claims were covered.
3. **Lexical/entity check**: ensure essential terms, numbers, names, and definitions appear or have close synonyms.
4. **Contradiction check**: optionally use a local natural-language-inference model to detect answers that conflict with the ideal answer.

This maps naturally to your existing `Grade` dataclass: semantic similarity can drive a rough `correctness` score, claim coverage can drive `completeness`, and basic text-quality checks can approximate `clarity`. Your current app already stores `correctness`, `completeness`, `clarity`, and `missed_points`, so a local grader can produce the same session records without an API call. [spacy](https://spacy.io/api/doc)

## Practical scoring design

A simple starting formula:

\[
\text{overall} = 0.55 \times \text{semantic} + 0.35 \times \text{coverage} + 0.10 \times \text{key-term}
\]

Where:

- `semantic` is cosine similarity, clipped and rescaled to 0–5.
- `coverage` is the fraction of atomic ideal-answer claims matched above a threshold.
- `key-term` checks required entities, numbers, or terminology.

For example, if the ideal answer contains:

- “Inflation reduces purchasing power.”
- “Central banks may raise interest rates.”
- “Higher rates can cool demand.”

Then the evaluator should score each point separately. A response saying, “Higher interest rates reduce spending and make money less able to buy things” should receive high semantic similarity and cover two claims, even though it uses different wording.

## Better than plain embeddings

For **claim-level feedback**, embed each required point separately rather than embedding the whole ideal answer once:

```python
claims = [
    "Inflation reduces purchasing power.",
    "Central banks may raise interest rates.",
    "Higher rates can cool demand.",
]

user_embedding = model.encode(user_answer, normalize_embeddings=True)
claim_embeddings = model.encode(claims, normalize_embeddings=True)

similarities = util.cos_sim(user_embedding, claim_embeddings)[0]

covered = [
    claim for claim, score in zip(claims, similarities)
    if score >= 0.55
]

missed = [
    claim for claim, score in zip(claims, similarities)
    if score < 0.55
]
```

This gives you useful `missed_points` locally: it identifies which component of the model answer your response did not sufficiently address. Sentence Transformers explicitly supports semantic textual similarity and pairwise similarity calculations. [sbert](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)

## When embeddings are enough

Embeddings work well for **recall and comprehension questions**, where the ideal answer is a short set of facts or explanations. They are less reliable for inference and synthesis questions, where a valid response may introduce relevant connections not present in the reference answer.

For those question types, treat the local score as a **signal, not a verdict**:

- High similarity: likely strong answer.
- Medium similarity: inspect the missed claims.
- Low similarity: either genuinely incomplete, phrased very differently, or answering a related but different point.

A local cross-encoder can improve pairwise judgement, but it is still fundamentally comparing text similarity rather than reasoning like a tutor. Sentence Transformers describes cross-encoders as rerankers that can refine results after an initial embedding-based pass. [sbert](https://www.sbert.net/docs/sentence_transformer/usage/usage.html)

## Recommended implementation

For your Brain Gym app, I would:

- Keep the LLM for **question generation** and optional rich feedback.
- Add a local `grade_answer_local()` function using Sentence Transformers.
- Require each question to include an `ideal_answer` and a list of `key_points`.
- Use cosine similarity for the overall semantic score.
- Use per-key-point similarity for `completeness` and `missed_points`.
- Use a conservative threshold, such as 0.50–0.60, and show the matched/missed points rather than pretending the number is a precise grade.
- Optionally add an NLI model only if you need contradiction detection.

This would make the app work offline for grading while preserving the interactive recall loop already in `active_reading.py`. [spacy](https://spacy.io/api/doc)



