# Clannon Universal Media Intelligence Architecture

> **Purpose:** The media-native architecture — how any modality becomes shared,
> regenerable knowledge instead of throwaway summaries.
> **Scope:** Universal Asset model, per-modality representations, multi-embedding
> strategy, knowledge graph, provider abstraction, local-first resilience.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Status:** target/aspirational — see the scope note in [README.md](README.md);
> current build is narrower. Tracked proposal:
> [../../decisions/proposed/0005-cross-media-knowledge-graph.md](../../decisions/proposed/0005-cross-media-knowledge-graph.md).
> **Related:** [README.md](README.md) ·
> [../../vision/ATTENTION_THRESHOLD.md](../../vision/ATTENTION_THRESHOLD.md)
> (Pillar 2) · [../memory/](../memory/)

## Building a Media-Native System That Never Reduces Reality to Text

Version: 1.0

---

# Mission

Build the most robust media understanding platform possible.

The system must:

* Process every major media type.
* Preserve original information.
* Never treat text as the canonical representation.
* Operate with OpenAI, Gemini, Claude, local models, or any combination.
* Gracefully degrade when providers disappear.
* Continue functioning even with zero API keys.
* Maintain long-term memory and cross-modal relationships.
* Allow future models to reprocess original data without loss.

---

# Core Principle

**Text is a view, not the truth.**

Never perform:

```text
Video
→ Transcript
→ Delete Video Context
→ LLM
```

Instead:

```text
Video
├── Original Asset
├── Frames
├── Audio
├── Motion
├── Scene Graph
├── Embeddings
├── Transcript
└── Metadata
```

Every representation survives.

Nothing is discarded.

---

# Canonical Architecture

```text
                    Ingestion
                         │
                         ▼
               Asset Normalization
                         │
                         ▼
            Representation Generation
                         │
                         ▼
                Embedding Pipeline
                         │
                         ▼
             Knowledge Graph Builder
                         │
                         ▼
                 Memory Formation
                         │
                         ▼
                Reasoning Engine
                         │
                         ▼
                     Agents
```

---

# First Principle

The platform does not store files.

The platform stores reality.

Files are merely one view of reality.

Every asset becomes:

```typescript
Asset {
    id
    type
    raw_location

    metadata

    representations[]

    embeddings[]

    entities[]

    relationships[]

    lineage[]

    timestamps
}
```

---

# Storage Architecture

## Raw Storage

Purpose:

Permanent immutable source of truth.

Requirements:

* Versioned
* Content-addressed
* Never modified

Recommended:

```text
S3
Cloudflare R2
MinIO
```

Structure:

```text
/raw
/images
/video
/audio
/documents
/code
/web
```

---

## Metadata Database

Purpose:

Fast retrieval.

Recommended:

```text
Postgres
```

Stores:

```text
asset metadata
timestamps
owners
permissions
representation pointers
processing status
```

---

## Vector Database

Purpose:

Cross-modal similarity.

Recommended:

```text
Qdrant
```

Fallback:

```text
Weaviate
Milvus
pgvector
```

Stores:

```text
text embeddings
image embeddings
audio embeddings
video embeddings
code embeddings
entity embeddings
```

---

## Graph Database

> **Superseded (2026-06-26):** the graph engine is resolved to **Kuzu** in
> [../../ARCHITECTURE.md](../../ARCHITECTURE.md) §5.2 (embedded, Cypher, behind a
> GraphPort; Qdrant remains the vector layer). Neo4j is retained only as a future
> scale-up swap. The recommendation below is updated accordingly.

Purpose:

Reality relationships.

Recommended:

```text
Kuzu   (resolved — see ARCHITECTURE.md §5.2)
```

Alternatives:

```text
Neo4j   (future scale-up swap)
Memgraph
```

Stores:

```text
person knows person
document cites paper
video contains event
image contains object
conversation references document
```

---

# Universal Asset Model

Every media object becomes:

```typescript
UniversalAsset {
    id

    raw_asset

    modality

    representations

    embeddings

    entities

    graph_links

    provenance

    confidence_scores
}
```

---

# Supported Modalities

Must support:

```text
Text
Markdown
PDF
DOCX
HTML
Email

Image
PNG
JPG
WEBP
TIFF

Audio
WAV
MP3
FLAC
AAC

Video
MP4
MOV
MKV
WEBM

Code
All major languages

Spreadsheet
XLSX
CSV

Presentation
PPTX

CAD
3D
GLB
OBJ

Scientific
NetCDF
HDF5

Medical
DICOM

Archives
ZIP
TAR
```

Architecture must allow unlimited future modalities.

---

# Representation Layer

Most important subsystem.

Representations are additive.

Never destructive.

---

# Image Representations

Generate:

```text
ImageEmbedding

Caption

DenseCaption

Objects

BoundingBoxes

SegmentationMasks

OCR

SceneGraph

Faces

Landmarks

ColorProfile

PerceptualHash
```

Store all.

---

# Video Representations

Generate:

```text
Keyframes

SceneBoundaries

AudioTrack

Transcript

ObjectTracking

MotionVectors

TemporalEvents

VideoEmbeddings

ShotClassification

EntityTimeline

SceneGraph
```

Maintain timestamps everywhere.

Never lose temporal structure.

---

# Audio Representations

Generate:

```text
Transcript

SpeakerDiarization

EmotionSignals

AcousticEmbedding

MusicFeatures

EventDetection

LanguageDetection

ProsodyAnalysis
```

Store waveform references.

---

# PDF Representations

Generate:

```text
LayoutGraph

ExtractedText

Tables

Figures

Images

References

Equations

DocumentStructure

Sections

Footnotes
```

Never flatten PDFs into plain text.

---

# Code Representations

Generate:

```text
AST

DependencyGraph

Imports

Exports

Symbols

Functions

Classes

CodeEmbeddings

CallGraph
```

Store semantic structure.

---

# Web Page Representations

Generate:

```text
DOM Tree

Rendered Screenshot

Accessibility Tree

Structured Data

Extracted Text

Links

Interactive Components
```

---

# Knowledge Graph

Every representation contributes facts.

Example:

```text
Video123
contains
Person456

Person456
mentioned_in
Document789

Document789
cites
PaperABC

PaperABC
written_by
ResearcherXYZ
```

The graph becomes long-term memory.

---

# Embedding Strategy

Never use one embedding model.

Store multiple embedding spaces.

Example:

```text
OpenAI Embedding

Gemini Embedding

Local BGE

Jina Embedding

Future Embeddings
```

Store all.

Reason:

Embedding models become obsolete.

Raw assets survive.

Representations survive.

Embeddings can be regenerated.

---

# Provider Abstraction Layer

Never let business logic know providers exist.

Create capability interfaces.

Example:

```typescript
VisionProvider

AudioProvider

VideoProvider

OCRProvider

ReasoningProvider

EmbeddingProvider
```

Business logic calls:

```typescript
vision.detectObjects(asset)
```

Not:

```typescript
openai.detectObjects(asset)
```

---

# Capability Routing

Dynamic routing.

Example:

```text
Need OCR

PaddleOCR available?
    yes

Else Gemini?
    yes

Else OpenAI?
    yes

Else fail
```

Capability first.

Provider second.

---

# Local-First Resilience

System must operate with:

```text
0 API keys
0 internet
0 cloud services
```

Reduced quality is acceptable.

Failure is not.

---

# Local Model Stack

## OCR

```text
PaddleOCR
Surya
Tesseract
```

---

## Images

```text
Florence-2

CLIP

GroundingDINO

SAM2
```

---

## Audio

```text
Whisper

Parakeet

pyannote
```

---

## Video

```text
InternVideo2

VideoLLaMA

VideoPrism
```

---

## Documents

```text
Docling

MinerU

Marker
```

---

## Embeddings

```text
BGE

E5

NV-Embed

Jina
```

---

## Reranking

```text
BGE Reranker

Jina Reranker
```

---

# Processing Pipeline

Every asset passes through:

```text
1 Ingest
2 Normalize
3 Fingerprint
4 Extract Representations
5 Generate Embeddings
6 Extract Entities
7 Build Relationships
8 Store
9 Verify
10 Publish
```

---

# Reprocessing Philosophy

Representations are disposable.

Assets are not.

When better models appear:

```text
Reprocess Representations
Keep Original Asset
```

Never lose future optionality.

---

# Memory Architecture

Three levels.

---

## Episodic Memory

Stores:

```text
Conversations
Events
User Actions
Sessions
```

---

## Semantic Memory

Stores:

```text
Facts
Concepts
Relationships
```

---

## Procedural Memory

Stores:

```text
Workflows
Tools
Agent Behaviors
Strategies
```

---

# Agent Architecture

Agents never access raw databases directly.

Agents query:

```text
Memory API

Graph API

Search API

Representation API
```

This prevents architecture coupling.

---

# Search System

Search is multi-modal.

A query may search:

```text
Text

Images

Audio

Video

Documents

Code

Graph Relationships
```

Simultaneously.

---

# Temporal Intelligence

Every event receives:

```text
start_time

end_time

source

confidence
```

This is mandatory.

Time is a first-class primitive.

---

# Provenance Tracking

Every fact must know:

```text
where it came from

which model produced it

when it was generated

confidence level
```

No orphaned facts.

---

# Security

Mandatory.

---

## Encryption

```text
AES-256 at rest

TLS in transit
```

---

## Access Control

```text
Asset level

Representation level

Graph level
```

---

## Audit Trails

Track:

```text
who accessed

when

why

what changed
```

---

# Observability

Every stage emits:

```text
latency

token usage

provider

model

cost

success

failure
```

Store permanently.

---

# Future-Proofing Rules

Rule 1:

Never trust one provider.

Rule 2:

Never trust one model.

Rule 3:

Never trust one embedding space.

Rule 4:

Never trust one representation.

Rule 5:

Never discard raw data.

Rule 6:

Every representation is replaceable.

Rule 7:

Knowledge graphs outlive models.

Rule 8:

Assets are forever.

Rule 9:

Text is not reality.

Rule 10:

The system should become smarter when models improve without requiring re-ingestion.

---

# Success Criteria

A successful architecture can:

* Understand any media.
* Preserve information indefinitely.
* Operate online or offline.
* Switch providers instantly.
* Reprocess assets with future models.
* Perform cross-modal retrieval.
* Maintain long-term memory.
* Build relationships across all knowledge.
* Never require text as the canonical representation.

The objective is not to build a chatbot.

The objective is to build a persistent, modality-native intelligence layer for reality itself.
