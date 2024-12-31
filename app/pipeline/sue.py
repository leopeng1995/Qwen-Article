from qwergpt.pipelines import Pipeline

from app.preprocessor import Preprocessor
from app.law.lawsue import LawSue


class SuePipeline(Pipeline):
    async def run(self, question: str) -> str:
        preprocessor = Preprocessor()
        question = await preprocessor.run(question)

        lawsue = LawSue()
        return await lawsue.run(question)
