# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/FrostWillmott/FinDocBot/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/findocbot/adapters/api/routes.py                       |       47 |        0 |        6 |        0 |    100% |           |
| src/findocbot/adapters/api/schemas.py                      |       14 |        0 |        0 |        0 |    100% |           |
| src/findocbot/config.py                                    |       15 |        0 |        0 |        0 |    100% |           |
| src/findocbot/domain/entities.py                           |       21 |        0 |        0 |        0 |    100% |           |
| src/findocbot/domain/exceptions.py                         |        6 |        0 |        0 |        0 |    100% |           |
| src/findocbot/infrastructure/cached\_embedding\_gateway.py |       62 |        0 |       10 |        0 |    100% |           |
| src/findocbot/infrastructure/chunking.py                   |       90 |        1 |       34 |        5 |     95% |103-\>105, 133-\>138, 151-\>159, 154-\>156, 166 |
| src/findocbot/infrastructure/container.py                  |       33 |        0 |        0 |        0 |    100% |           |
| src/findocbot/infrastructure/db.py                         |       17 |        8 |        6 |        0 |     39% |16-17, 23-25, 30-32 |
| src/findocbot/infrastructure/in\_memory.py                 |       36 |        0 |        4 |        0 |    100% |           |
| src/findocbot/infrastructure/ollama\_gateway.py            |       54 |        0 |       12 |        0 |    100% |           |
| src/findocbot/infrastructure/pdf\_parser.py                |        7 |        0 |        0 |        0 |    100% |           |
| src/findocbot/infrastructure/postgres\_repositories.py     |       55 |       34 |        4 |        0 |     36% |12, 24-35, 39-45, 61-95, 103-122, 146-165, 169-193 |
| src/findocbot/main.py                                      |       21 |        1 |        2 |        0 |     96% |        41 |
| src/findocbot/use\_cases/answer\_question.py               |       35 |        0 |        2 |        0 |    100% |           |
| src/findocbot/use\_cases/dto.py                            |        8 |        0 |        0 |        0 |    100% |           |
| src/findocbot/use\_cases/ports.py                          |       24 |        0 |        0 |        0 |    100% |           |
| src/findocbot/use\_cases/search\_similar\_chunks.py        |       14 |        0 |        2 |        0 |    100% |           |
| src/findocbot/use\_cases/upload\_pdf.py                    |       26 |        0 |        2 |        0 |    100% |           |
| **TOTAL**                                                  |  **585** |   **44** |   **84** |    **5** | **91%** |           |


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