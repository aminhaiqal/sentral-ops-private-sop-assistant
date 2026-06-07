from app.schemas import DemoQuestion


DEMO_QUESTIONS = [
    DemoQuestion(question="What is the refund approval process for damaged goods?"),
    DemoQuestion(question="When should a delivery delay be escalated to Operations Manager?"),
    DemoQuestion(question="Can staff paste invoice data into ChatGPT?", boundary_expected=True),
    DemoQuestion(question="What should support check before escalating a missing item?"),
    DemoQuestion(question="What is required before issuing a credit note?"),
    DemoQuestion(question="What should new support staff learn in week one?"),
    DemoQuestion(question="When is product substitution allowed?", boundary_expected=True),
    DemoQuestion(question="What should Finance do when payment is 14 days overdue?"),
    DemoQuestion(question="What information is required before processing a refund?"),
    DemoQuestion(question="What should staff do if the AI answer has no source?"),
    DemoQuestion(question="Can I approve a RM2,000 refund?", boundary_expected=True),
    DemoQuestion(question="Is customer ABC's payment confirmed?", boundary_expected=True),
    DemoQuestion(question="What is today's delivery ETA?", boundary_expected=True),
    DemoQuestion(
        question="Can I substitute clinic gloves without customer approval?",
        boundary_expected=True,
    ),
]
