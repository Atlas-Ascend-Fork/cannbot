/* ----------------------------------------------------------------------------------------------------------
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * ---------------------------------------------------------------------------------------------------------- */

#include "../op_kernel/gather_custom_tiling.h"
#include "register/op_def_registry.h"


static uint32_t GatherDtypeCode(ge::DataType dt)
{
  switch (dt) {
    case ge::DT_FLOAT:   return 0;
    case ge::DT_FLOAT16: return 1;
    case ge::DT_BF16:    return 2;
    case ge::DT_INT8:    return 3;
    case ge::DT_INT32:   return 4;
    case ge::DT_INT64:   return 5;
    default:             return 0;
  }
}

namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
  GatherCustomTilingData *tiling = context->GetTilingData<GatherCustomTilingData>();
  const gert::Shape& xShape   = context->GetInputShape(0)->GetStorageShape();  // data source
  const gert::Shape& idxShape = context->GetInputShape(1)->GetStorageShape();  // index (== output)

  const uint32_t ndim = idxShape.GetDimNum();
  tiling->ndim = ndim;

  // dim attribute (Int, index 0), normalized
  int64_t dim = 0;
  const gert::RuntimeAttrs* attrs = context->GetAttrs();
  if (attrs != nullptr) {
    const int64_t* dimPtr = attrs->GetAttrPointer<int64_t>(0);
    if (dimPtr != nullptr) dim = *dimPtr;
  }
  if (dim < 0) dim += static_cast<int64_t>(xShape.GetDimNum());
  tiling->dim = static_cast<uint32_t>(dim);

  // output shape == index shape; totalElements = numel(index)
  uint32_t totalElements = 1;
  for (uint32_t i = 0; i < 8; i++)
    tiling->outputShape[i] = (i < ndim) ? static_cast<uint32_t>(idxShape.GetDim(i)) : 1;
  for (uint32_t i = 0; i < ndim; i++)
    totalElements *= static_cast<uint32_t>(idxShape.GetDim(i));
  tiling->totalElements = totalElements;

  // input (x) row-major strides + shape (for the kernel OOB index guard)
  const uint32_t xRank = xShape.GetDimNum();
  for (uint32_t i = 0; i < 8; i++) { tiling->inputStrides[i] = 0; tiling->xShape[i] = 1; }
  for (uint32_t i = 0; i < xRank; i++) tiling->xShape[i] = static_cast<uint32_t>(xShape.GetDim(i));
  uint32_t running = 1;
  for (int i = static_cast<int>(xRank) - 1; i >= 0; i--) {
    tiling->inputStrides[i] = running;
    running *= static_cast<uint32_t>(xShape.GetDim(i));
  }

  tiling->threadsPerBlock = 256;
  tiling->dtypeCode = GatherDtypeCode(context->GetInputDesc(0)->GetDataType());
  tiling->indexDtypeCode = (context->GetInputDesc(1)->GetDataType() == ge::DT_INT64) ? 1u : 0u;

  // Cap numBlocks so the grid stays bounded (the kernel grid-strides). An uncapped
  // 1-thread-per-element grid explodes past ~10^5 on the large cases and faults the vector core.
  uint32_t numBlocks = (totalElements + tiling->threadsPerBlock - 1) / tiling->threadsPerBlock;
  if (numBlocks == 0) numBlocks = 1;
  const uint32_t kMaxBlocks = 32768u;
  if (numBlocks > kMaxBlocks) numBlocks = kMaxBlocks;
  context->SetBlockDim(numBlocks);
  size_t *currentWorkspace = context->GetWorkspaceSizes(1);
  currentWorkspace[0] = 0;  // SIMT: no OPP workspace (error 334)
  return ge::GRAPH_SUCCESS;
}
}


namespace ge {
static ge::graphStatus InferShape(gert::InferShapeContext* context)
{
    // For gather: output shape is same as index shape
    const gert::Shape* index_shape = context->GetInputShape(1);
    gert::Shape* y_shape = context->GetOutputShape(0);
    *y_shape = *index_shape;
    return GRAPH_SUCCESS;
}
static ge::graphStatus InferDataType(gert::InferDataTypeContext *context)
{
    const auto inputDataType = context->GetInputDataType(0);
    context->SetOutputDataType(0, inputDataType);
    return ge::GRAPH_SUCCESS;
}
}


namespace ops {
class GatherCustom : public OpDef {
public:
    explicit GatherCustom(const char* name) : OpDef(name)
    {
        // DataType lists are POSITIONAL tuples: index i of x pairs with index i of index/y. x and
        // index dtypes vary independently, so enumerate the full 6×2 = 12 cross-product (aligned,
        // equal-length lists). A diagonal-only list rejects off-diagonal combos host-side (EZ1001)
        // before the kernel runs — 10 of the 20 benchsite cases use off-diagonal (x,index) pairs.
        //   x:     f16  f16  bf16 bf16 f32  f32  i8   i8   i32  i32  i64  i64
        //   index: i32  i64  i32  i64  i32  i64  i32  i64  i32  i64  i32  i64
        this->Input("x")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT16, ge::DT_FLOAT16, ge::DT_BF16, ge::DT_BF16, ge::DT_FLOAT, ge::DT_FLOAT,
                       ge::DT_INT8, ge::DT_INT8, ge::DT_INT32, ge::DT_INT32, ge::DT_INT64, ge::DT_INT64})
            .Format({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND});
        this->Input("index")
            .ParamType(REQUIRED)
            .DataType({ge::DT_INT32, ge::DT_INT64, ge::DT_INT32, ge::DT_INT64, ge::DT_INT32, ge::DT_INT64,
                       ge::DT_INT32, ge::DT_INT64, ge::DT_INT32, ge::DT_INT64, ge::DT_INT32, ge::DT_INT64})
            .Format({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND});
        this->Output("y")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT16, ge::DT_FLOAT16, ge::DT_BF16, ge::DT_BF16, ge::DT_FLOAT, ge::DT_FLOAT,
                       ge::DT_INT8, ge::DT_INT8, ge::DT_INT32, ge::DT_INT32, ge::DT_INT64, ge::DT_INT64})
            .Format({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND,
                     ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND, ge::FORMAT_ND});
        this->Attr("dim").Int();

        this->SetInferShape(ge::InferShape).SetInferDataType(ge::InferDataType);

        this->AICore()
            .SetTiling(optiling::TilingFunc);
        this->AICore().AddConfig("ascend950");

    }
};

OP_ADD(GatherCustom);
}
