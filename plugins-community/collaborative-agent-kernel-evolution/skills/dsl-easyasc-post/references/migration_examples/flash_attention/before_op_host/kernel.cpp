/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "kernel_tiling.h"
#include "register/op_def_registry.h"
#include "tiling/tiling_api.h"

#define SET_ATTR_TO_TILING(name, dtype, idx) \
    const auto* name##_ptr = attrs->GetAttrPointer<dtype>(idx); \
    dtype name = *name##_ptr; \
    tiling.set_##name(name);
#define GET_ATTR_BY_IDX(name, dtype, idx) \
    const auto* name##_ptr = attrs->GetAttrPointer<dtype>(idx); \
    dtype name = *name##_ptr;

namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{
    // set block size
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
    context->SetBlockDim(20);

    KernelTilingData tiling;
    auto attrs = context->GetAttrs();
    SET_ATTR_TO_TILING(S1, int32_t, 0);
    SET_ATTR_TO_TILING(S2, int32_t, 1);
    SET_ATTR_TO_TILING(D, int32_t, 2);
    SET_ATTR_TO_TILING(BH, int32_t, 3);
    SET_ATTR_TO_TILING(scale, float, 4);
    tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
    context->GetRawTilingData()->SetDataSize(tiling.GetDataSize());

    size_t userWorkspaceSize = (0 * 2 * 128 * 128) * sizeof(float) + (0 * 2 * 128 * 128) * sizeof(uint16_t) + (0 * 2 * 128 * 128) * sizeof(float);
    size_t sysWorkspaceSize = static_cast<size_t>(ascendcPlatform.GetLibApiWorkSpaceSize());
    size_t *currentWorkspace = context->GetWorkspaceSizes(1);
    currentWorkspace[0] = userWorkspaceSize + sysWorkspaceSize;
    return ge::GRAPH_SUCCESS;
}
}

namespace ge {
static ge::graphStatus InferShape(gert::InferShapeContext* context)
{
    (void)context;
    return GRAPH_SUCCESS;
}

static ge::graphStatus InferDataType(gert::InferDataTypeContext* context)
{
    (void)context;
    return GRAPH_SUCCESS;
}
}

namespace ops {
class Kernel : public OpDef {
public:
    explicit Kernel(const char* name) : OpDef(name)
    {
        this->Input("q")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT16})
            .Format({ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND});
        this->Input("k")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT16})
            .Format({ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND});
        this->Input("v")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT16})
            .Format({ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND});
        this->Output("out")
            .ParamType(REQUIRED)
            .DataType({ge::DT_FLOAT})
            .Format({ge::FORMAT_ND})
            .UnknownShapeFormat({ge::FORMAT_ND});
        this->Attr("S1")
            .AttrType(REQUIRED)
            .Int(0);
        this->Attr("S2")
            .AttrType(REQUIRED)
            .Int(0);
        this->Attr("D")
            .AttrType(REQUIRED)
            .Int(0);
        this->Attr("BH")
            .AttrType(REQUIRED)
            .Int(0);
        this->Attr("scale")
            .AttrType(REQUIRED)
            .Float(0);
        this->SetInferShape(ge::InferShape).SetInferDataType(ge::InferDataType);

        this->AICore().SetTiling(optiling::TilingFunc);
        this->AICore().AddConfig("ascend910b");
    }
};

OP_ADD(Kernel);
}
