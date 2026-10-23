# Affine Access Degraded To Indirect

## Purpose

Detect a regular tile access that becomes an indirect gather/scatter during
lowering because per-lane clamps hide its affine structure from the compiler.
This is an IR diagnosis pattern, not a source optimization pattern. Route a
confirmed match to `mask-only-affine-addressing`.

## IR Signature

Look for this evidence chain in one stage or across ordered stages:

1. The index originates from `program_id` plus `make_range` and constant-stride
   arithmetic.
2. A per-lane `min`, `max`, or `select` clamps the index to an extent boundary.
3. A comparison or mask already predicates the same logical boundary.
4. A later stage emits `triton_indirect_load` or `triton_indirect_store`.

Conceptually:

```text
offset = block_offset + make_range
safe   = min(offset, extent - 1)
valid  = offset < extent
ptr    = base + safe * stride
load(ptr, mask=valid)
                    |
                    v
triton_indirect_load
```

The clamp makes each lane's address look selected independently even though
the valid lanes still form a regular slice. The indirect operation is the
compiler symptom; it does not by itself prove a specific physical DMA path.

## Confidence

- **High**: affine origin, clamp, mask, and indirect operation remain visible
  in the same stage.
- **Medium**: affine origin, clamp, and mask occur in an earlier ordered stage,
  while the indirect operation appears later.
- Do not classify an access under this pattern when only the indirect
  operation is visible without affine provenance.

Text co-occurrence is navigation evidence, not a complete def-use proof.
Before changing code, inspect the cited lines and confirm that the clamp and
mask feed the same access.

## Non-Match: Genuine Gather

Do not classify an access as degraded affine addressing when the index comes
from another load, lookup table, sort result, or data-dependent computation:

```text
indices = load(index_ptr)
values  = triton_indirect_load(base, indices)
```

That is a genuine gather. Its addresses cannot be made affine by deleting a
boundary clamp; route it toward staging or `discrete-access-ub-staging` instead.

## Runtime Corroboration

The IR pattern becomes a strong bottleneck diagnosis when profile evidence
also shows:

- high `aiv_vec_ratio`,
- low `aic_mac_ratio` for a GEMM-family kernel,
- low MTE ratios,
- and measured time far above a moved-bytes / bandwidth lower bound.

These ratios are corroboration, not required for the IR detector. They explain
why reducing storage bytes may fail while simplifying address generation wins.

## Verification

After applying `mask-only-affine-addressing`, compare parent and candidate IR:

- the targeted `triton_indirect_load` / `triton_indirect_store` disappears,
- the per-lane clamp on the address path disappears,
- the boundary predicate remains,
- matrix/vector compute structure and logical data volume remain unchanged,
- and correctness is bit-exact.

