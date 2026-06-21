# ADR-002: Professional Financial Chart Style

**Date**: 2025-11-26
**Status**: Accepted
**Related**: [[pipeline]], [[dataspec]]

## Context

LLM-generated charts tend to adopt a "teaching presentation style":
- Automatically annotate historical events like "2008 Financial Crisis"
- Annotate extreme points ("Historical high X%")
- Colored area highlights
- Numerous explanatory text boxes

This differs significantly from the style of real financial charts (Bloomberg/FRED). A decision is needed on whether to impose constraints.

## Decision

Pursue a **professional financial style**, with explicit constraints in the prompts:
- Prohibit decorative annotations (extreme point labels, colored highlights, explanatory text boxes)
- Allow functional annotations (Y=0 reference lines, recession shadows, small-font values at the end of curves)
- Set an "annotation budget" (maximum 1-2 additional annotations)

## Rationale

**Reasons for this decision**:
- Training data should approximate real-world distributions
- A minimalist style lets the data speak for itself, making it harder for the model to "cheat"
- A professional style is more suitable for financial application scenarios

**Rejected alternatives**:
- No constraints at all: LLMs over-decorate, data gets lost in annotations
- Completely prohibit all annotations: might be too simplistic (user feedback concerns)

**Balance point**:
- Minimalist by default
- Limited functional annotation options
- General principles rather than specific rules (to avoid overfitting to specific business examples)

## Consequences

### Positive
- Charts are more professional, closer to the output of real financial institutions
- The model needs to truly understand the data, rather than relying on annotations

### Negative/Costs
- Some complex charts might "appear simple"
- Requires careful balancing of constraint intensity in prompts
