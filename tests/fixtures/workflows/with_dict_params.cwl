cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, train.py]

inputs:
  # Dict value mapping: scaling decision with value: {method: "standard", with_mean: true}
  # should map to scaling_method and scaling_with_mean
  scaling_method:
    type: string
    doc: "Scaling method"

  scaling_with_mean:
    type: boolean?
    doc: "Whether to center the data"

  model:
    type: string
    doc: "Model type"

  test_size:
    type: float
    doc: "Test split size"

outputs:
  result:
    type: File
    outputBinding:
      glob: result.json
