# Translation Model And Licence Research

Reviewed: 2026-07-20

This review covers local translation for Church Cap v0.7.0. The requirements are offline inference during a service, source-available/open-source components, commercial-use-compatible terms, broad language coverage, predictable Chinese script output, and acceptable latency on the Linux reference computer. This is an engineering review, not legal advice; licences must be checked again for every model artifact included in a distributed image.

## Implemented Decision

Church Cap keeps SMaLL-100 as the recommended broad-language model and adds a provider-independent Chinese finalisation step:

- `zh-Hans` translates through the provider's Chinese target and then uses OpenCC `t2s` to enforce Simplified Chinese.
- `zh-Hant` translates through the provider's Chinese target and then uses OpenCC `s2hk` to enforce Hong Kong Traditional characters and regional variants.
- Argos prefers its `zt` target for `zh-Hant` and `zh` for `zh-Hans`, but can use either installed Chinese package because OpenCC enforces the final script.
- SMaLL-100 exposes only one model-level `zh` target, so both audience choices use that target before deterministic conversion.
- Legacy `zh` settings migrate to `zh-Hans`; browser locales such as `zh-HK` and `zh-TW` select `zh-Hant`.

OpenCC is a conversion library, not a translator between Mandarin and Cantonese. Native Hong Kong review is still required for vocabulary, naturalness, theology, names, and meaning.

## Contextual Translation

Prompt instructions are not reliable across the current providers: Argos and SMaLL-100 are sequence-to-sequence translation systems rather than instruction-following chat models. The completed-thought Contextual and Extended experiments also produced excessive user-visible delay because they waited for two or four sealed English units before translation began.

Church Cap now uses **Responsive Context**, a provider-independent retranslation strategy. Once at least three words in the current English live cue have survived local agreement, that stable prefix is translated. A subsequent translation normally requires at least 1.5 seconds and three additional stable words. Queue coalescing removes an obsolete revision, and the full final English cue produces an in-place final refinement under the same cue ID. This follows the retranslation pattern described by [Google Research](https://research.google/blog/stabilizing-live-speech-translation-in-google-translate/) and evaluated for simultaneous caption translation in the [IWSLT retranslation study](https://aclanthology.org/2020.iwslt-1.27/), without adding a network service or retaining sermon text.

CTranslate2 supports target prefixes and prefix biasing, but Church Cap does not force the previously displayed target text yet. Over-biasing could preserve an incorrect translation, and Argos does not expose an equivalent provider-independent contract. The current implementation instead uses stable source words, cue-led replacement, and a small explicitly mutable target tail. Target-prefix bias remains an A/B experiment for the CTranslate2 provider. See the [CTranslate2 Translator API](https://opennmt.net/CTranslate2/python/ctranslate2.Translator.html).

This first implementation uses accumulating context inside the current cue only. It does not prepend previous sentences: the existing models can translate or reorder the whole concatenated block without a dependable way to isolate the newest target sentence, especially for Farsi and Chinese. One previous sealed cue may be tested later, but only as a bounded experiment with native review and revision measurements.

## Licence And Capability Audit

| Component/model | Capability | Published licence | Church Cap decision |
| --- | --- | --- | --- |
| [SMaLL-100](https://huggingface.co/alirezamsh/small100) | 0.3B multilingual translation model, 101 languages, one generic `zh` target | MIT on the model card | Keep as Recommended CTranslate2 INT8 and Compatibility PyTorch providers. Suitable for commercial-use evaluation under the published model terms. |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | Offline OpenNMT translation with separate language packages; Chinese `zh`/`zt` packages may be available | Library code is MIT or CC0 | Keep as Base/fallback, but treat every downloaded model package as a separate licensed artifact. Do not claim all Argos model weights are commercially cleared without package-level verification. |
| [OpenCC](https://github.com/BYVoid/OpenCC) | Character-, phrase-, and regional-variant conversion, including `t2s` and Hong Kong `s2hk` | Apache-2.0 | Ship as the deterministic script enforcement layer for every provider. |
| [OPUS-MT English→Chinese](https://huggingface.co/Helsinki-NLP/opus-mt-en-zh) | Chinese-specific Marian model with explicit Simplified/Traditional target tokens | Apache-2.0 on its model card | Strong candidate for an optional Chinese quality package. Benchmark against SMaLL-100 + OpenCC before adding another runtime/model download. |
| [MADLAD-400 3B MT](https://huggingface.co/google/madlad400-3b-mt) | 400+ languages; substantially larger model | Apache-2.0 on its model card | Research candidate for powerful GPU systems. At 3B parameters it is not an appropriate default for the current CPU appliance, and its card says domain quality varies and production use has not been assessed. |
| [NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M) | Broad multilingual translation | CC-BY-NC-4.0 | Excluded from Church Cap's commercially usable provider list because the published weights are non-commercial. |
| [SeamlessM4T v2](https://huggingface.co/facebook/seamless-m4t-v2-large) | Multilingual speech/text translation | CC-BY-NC-4.0 | Excluded for the same non-commercial restriction and because Church Cap already has a local speech-to-text path. |

## Copyright And Domain Context

Church Cap does not bundle Bible translations, worship lyrics, sermon archives, or denomination-specific corpora as context. Responsive Context uses only the current in-memory English cue and does not add it or its translation to diagnostics. Operator glossary terms and future sermon-note context must be supplied by the church from material it has the right to use. Public-domain terminology and church-authored notes are preferred for any future tuning or retrieval feature.

## Acceptance Gates

Before the Responsive Context thresholds are treated as validated:

1. Run Responsive Context, Live, and More Stable on the same recording at least three times.
2. Compare p50/p95 `cue_first_translation_publish`, source-to-publish delay, revision publications, queue coalescing, and Stop drain accounting.
3. Have native Farsi and Hong Kong Traditional Chinese reviewers score completeness, naturalness, literalness, terminology, and reading comfort passage by passage.
4. Confirm `zh-Hans` contains no unintended Traditional characters and `zh-Hant` contains no unintended Simplified characters in the reviewed sample.
5. Aim for first translated cue p50 at or below 3 seconds and p95 at or below 5 seconds on the Linux reference appliance, with no completed translated cue changing or appearing twice.
6. Keep Responsive Context as the recommendation only if its context/readability benefit is confirmed without an unacceptable delay or revision rate.
