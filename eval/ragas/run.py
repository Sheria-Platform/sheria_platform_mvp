# eval/ragas/run.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from datasets import Dataset

def run_evaluation(questions, answers, contexts, ground_truths):
    """
    Runs the Ragas evaluation suite.
    """

    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts, 
        "ground_truth": ground_truths
    }

    dataset = Dataset.from_dict(data)

    results = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
    )
    

    df = results.to_pandas()

    df.to_csv("eval/reports/evaluation_results.csv", index=False)

    print(results)