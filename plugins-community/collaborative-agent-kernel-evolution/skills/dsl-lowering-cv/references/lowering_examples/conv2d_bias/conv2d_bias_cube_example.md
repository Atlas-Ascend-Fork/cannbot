### Example Input DSL (cube scope)
```python
with tl.scope('cube'):
    conv_shape = tl.make_conv_shape(batch, Ho, Wo, Cout)
    tl.conv2d_dot(
        fmap, layout_fmap,
        weight, layout_weight,
        output, layout_out,
        conv_shape, conv_params
    )
```

### Example Output (KernelCube using ConvBias)
```cpp
class KernelCube {
public:
  __aicore__ inline void Init(GM_ADDR fmap, GM_ADDR filter, GM_ADDR bias, GM_ADDR output,
                              uint32_t batch, uint32_t Cin, uint32_t H, uint32_t W,
                              uint32_t Cout, uint32_t kH, uint32_t kW,
                              uint32_t strideH, uint32_t strideW,
                              uint32_t padH, uint32_t padW,
                              uint32_t Ho, uint32_t Wo,
                              uint32_t Cin1, uint32_t Cout1)
  {
    constexpr uint32_t C0 = 16;
    constexpr uint32_t N0 = 16;

    // Construct Conv3dParams (Conv2d = Conv3d with D=1, Kd=1)
    uint32_t N1 = Cout1;
    problemShape = Conv3dParams(
        batch,          // BATCH
        1,              // Di = 1 (2D conv)
        Cin1,           // Cin1
        H, W, C0,      // Hi, Wi, C0
        1,              // Kd = 1 (2D conv)
        kH, kW,         // Kh, Kw
        N1,             // N1 = Cout1
        1,              // Do = 1 (2D conv)
        Ho, Wo,         // Ho, Wo
        Cout1,          // Cout1
        Cout,           // Cout
        0,              // padHead = 0 (no depth padding)
        padH, padW,     // padTop, padLeft
        1,              // strideD = 1
        strideH, strideW, // strideH, strideW
        1, 1, 1         // dilationD, dilationH, dilationW
    );

    // Set up global memory tensors
    ptrFmap = fmap;
    ptrFilter = filter;
    ptrBias = bias;
    ptrOutput = output;
  }

  __aicore__ inline void Process()
  {
    // Construct layouts for each tensor
    uint32_t Cin1 = problemShape.cin1();
    uint32_t kH = problemShape.kh();
    uint32_t kW = problemShape.kw();
    uint32_t N1 = problemShape.n1();
    constexpr uint32_t C0 = 16;
    constexpr uint32_t N0 = 16;

    LayoutFmap layoutFmap(problemShape.batch(), 1, Cin1,
                          problemShape.hi() * problemShape.wi(), C0);
    LayoutFilter layoutFilter(problemShape.kdc1khkw(), N1, N0, C0);
    LayoutOut layoutOut(problemShape.batch(), 1, problemShape.cout1(),
                        problemShape.ho() * problemShape.wo(), C0);

    // Prepare ConvKernel arguments and run
    typename ConvKernel::Arguments arguments{
        problemShape, ptrFmap, ptrFilter, ptrOutput, ptrBias
    };

    typename ConvKernel::Params params =
        ConvKernel::ToUnderlyingArguments(arguments, nullptr);

    ConvKernel convKernel;
    convKernel.template operator()<AscendC::AIC>(params);
  }

private:
  Conv3dParams problemShape;
  GM_ADDR ptrFmap, ptrFilter, ptrBias, ptrOutput;
};
```

### Key Patterns

1. **Conv3dParams for Conv2d**: Set `Di=1`, `Kd=1`, `Do=1`, `strideD=1`, `dilationD=1`, `padHead=0`. All other parameters map directly from Conv2d.

2. **ConvKernel handles everything**: The `ConvKernel::operator()<AscendC::AIC>()` call internally:
   - Creates a `BlockScheduler` to map task IDs to output tile coordinates
   - Iterates over assigned tiles using `BlockConv::operator()()`
   - BlockConv handles: GM→L1 copy (fmap + filter + bias), L1→L0A im2col (Load3Dv2), L1→L0B load, Mmad compute, bias addition via BT buffer, Fixpipe output to GM

3. **No manual tiling loop**: Unlike matmul examples that manually iterate `for taskId in range(...)`, ConvKernel + BlockScheduler handles task distribution internally.

4. **No workspace**: ConvBias outputs directly to the output tensor via Fixpipe.

5. **No CrossCoreSetFlag**: AIC-only pattern, no Cube↔Vector synchronization needed.

6. **Reference**: `catlass-master/examples/24_conv_bias/conv_bias.cpp` shows the complete host+device pattern.
