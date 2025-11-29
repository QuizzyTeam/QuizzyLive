import strawberry

@strawberry.type
class QuizInfoType:
    """
    Тип, який повертає інформацію про вікторину для інфо-модалки.
    """
    id: str
    title: str
    description: str
    createdAt: str
    updatedAt: str
    questionCount: int
    rating: int
