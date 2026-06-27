---
name: skills-must-be-self-contained
description: User does not want skills to depend on / cross-reference one another
metadata:
  type: feedback
---

In the claude-skills marketplace repo, the user does not want skills depending on one another (no cross-skill `Related:` pointers / "see other-skill" references).

**Why:** Each skill is loaded independently based on its trigger description; a dependency would leave an agent with a dangling pointer, and references rot when skills move or get reworded. Coupling between skills is to be avoided.

**How to apply:** When reviewing or authoring a SKILL.md, keep it self-contained — write any needed guidance inline rather than referencing a sibling skill. Overlapping/duplicated content across skills is an acceptable price for independence; resolve overlap by keeping each skill's scope distinct, not by linking them. (A `Related:` pointer to a section *within the same skill* is fine.)
