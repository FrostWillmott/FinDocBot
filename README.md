# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/FrostWillmott/FinDocBot/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/findocbot/adapters/api/routes.py                       |       96 |        0 |        6 |        0 |    100% |           |
| src/findocbot/adapters/api/schemas.py                      |       30 |        0 |        0 |        0 |    100% |           |
| src/findocbot/config.py                                    |       25 |        0 |        0 |        0 |    100% |           |
| src/findocbot/domain/entities.py                           |       41 |        0 |        0 |        0 |    100% |           |
| src/findocbot/domain/exceptions.py                         |       13 |        0 |        0 |        0 |    100% |           |
| src/findocbot/infrastructure/cached\_embedding\_gateway.py |       63 |        0 |       10 |        0 |    100% |           |
| src/findocbot/infrastructure/chunking.py                   |      103 |        1 |       40 |        5 |     96% |128-\>130, 158-\>163, 176-\>188, 183-\>185, 195 |
| src/findocbot/infrastructure/container.py                  |       47 |        0 |        2 |        0 |    100% |           |
| src/findocbot/infrastructure/db.py                         |       26 |       13 |        6 |        0 |     41% |21-22, 28-30, 35-37, 41-51 |
| src/findocbot/infrastructure/ollama\_gateway.py            |       99 |        0 |       20 |        0 |    100% |           |
| src/findocbot/infrastructure/pdf\_parser.py                |       70 |        0 |       14 |        0 |    100% |           |
| src/findocbot/infrastructure/postgres\_repositories.py     |      104 |       66 |       10 |        4 |     37% |23, 27, 44-58, 62-73, 77-88, 92-105, 109-116, 129-140, 149-\>exit, 162, 165, 169-197, 206-225, 249-256, 260-267, 271-290, 294-318 |
| src/findocbot/main.py                                      |       27 |        1 |        2 |        0 |     97% |        54 |
| src/findocbot/use\_cases/answer\_question.py               |       81 |        0 |        8 |        0 |    100% |           |
| src/findocbot/use\_cases/dto.py                            |       17 |        0 |        0 |        0 |    100% |           |
| src/findocbot/use\_cases/manage\_documents.py              |       17 |        0 |        4 |        0 |    100% |           |
| src/findocbot/use\_cases/ports.py                          |       32 |        0 |        0 |        0 |    100% |           |
| src/findocbot/use\_cases/prompt\_safety.py                 |       12 |        0 |        2 |        0 |    100% |           |
| src/findocbot/use\_cases/search\_similar\_chunks.py        |       15 |        0 |        2 |        0 |    100% |           |
| src/findocbot/use\_cases/upload\_pdf.py                    |       38 |        1 |        6 |        1 |     95% |        86 |
| **TOTAL**                                                  |  **956** |   **82** |  **132** |   **10** | **91%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/FrostWillmott/FinDocBot/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/FrostWillmott/FinDocBot/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/FrostWillmott/FinDocBot/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/FrostWillmott/FinDocBot/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FFrostWillmott%2FFinDocBot%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/FrostWillmott/FinDocBot/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.