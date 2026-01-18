cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, train.py]

# Only has some parameters - should detect unmapped decisions
inputs:
  model:
    type: string
    doc: "Model type"

  # Missing: test_split, seed, preprocessing

  # Extra required param not in ASP
  extra_required:
    type: string
    doc: "An extra required parameter"

outputs:
  result:
    type: File
    outputBinding:
      glob: result.json
