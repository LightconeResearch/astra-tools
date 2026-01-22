cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, train.py]

inputs:
  model:
    type: string
    doc: "Model type (rf, svm, lr)"

  test_split:
    type: float
    doc: "Test split ratio"

  seed:
    type: int
    doc: "Random seed"

  preprocessing:
    type: string?
    doc: "Preprocessing method (optional)"

outputs:
  accuracy:
    type: float
    outputBinding:
      glob: results/accuracy.txt
