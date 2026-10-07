FROM python:3.12-slim

WORKDIR /app

# 앱 코드와 샘플 데이터만 넣는다. 채점 테스트(tests/)는 이미지에 넣지 않는다 —
# Harbor가 에이전트 실행이 끝난 뒤 /tests 로 올린다.
COPY app/ /app/

RUN chmod +x /app/scripts/run_weekly.sh \
    && mkdir -p /app/data

ENV PYTHONDONTWRITEBYTECODE=1
