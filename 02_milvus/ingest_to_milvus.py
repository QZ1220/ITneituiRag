import re
import json
import os
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from openai import OpenAI
from pymilvus import (
    connections,
    FieldSchema, CollectionSchema, DataType,
    Collection, utility
)

# ----------------------------
# 1. 连接 Milvus
# ----------------------------
def connect_milvus(host: str = "localhost", port: str = "19530"):
    connections.connect(db_name="jobs_rag", host=host, port=port)
    print("✅ Connected to Milvus")

# 搜索和查询
# 1、大模型初始化
openai_client = OpenAI(
	base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
	api_key=os.getenv("DASHSCOPE_API_KEY")
)

@dataclass
class JobItem:
    id: int
    title: str
    jobName: str
    jobSalary: str
    salaryMin: float
    salaryMax: float
    salaryUnit: str
    jobEdu: str
    eduLevel: int
    textForEmbedding: str
    embedding: List[float]

# ----------------------------
# 2. 创建 Collection
# ----------------------------
def create_collection(collection_name: str = "job_postings", dim: int = 1024):
    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=1000),
        FieldSchema(name="job_name", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="job_salary", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="salary_min", dtype=DataType.FLOAT),
        FieldSchema(name="salary_max", dtype=DataType.FLOAT),
        FieldSchema(name="salary_unit", dtype=DataType.VARCHAR, max_length=10),
        FieldSchema(name="job_edu", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="job_url", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="edu_level", dtype=DataType.INT16),
        FieldSchema(name="text_for_embedding", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim)
    ]

    schema = CollectionSchema(fields, description="Job postings for RAG")
    collection = Collection(collection_name, schema)

    # 创建向量索引
    index_params = {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {"M": 8, "efConstruction": 64}
    }
    collection.create_index("embedding", index_params)
    print(f"✅ Collection '{collection_name}' created with dim={dim}")
    return collection

# ----------------------------
# 3. 薪资解析函数
# ----------------------------
def parse_salary(salary_str: str) -> Tuple[Optional[float], Optional[float], str]:
    salary_str = salary_str.strip()
    if "面议" in salary_str or "协商" in salary_str:
        return None, None, "面议"

    salary_clean = salary_str.lower().replace("w", "k").replace("万", "k")
    pattern = r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*[kK]\s*/\s*(年|月)'
    match = re.search(pattern, salary_clean)
    if not match:
        single_pattern = r'(\d+\.?\d*)\s*[kK]\s*/\s*(年|月)'
        smatch = re.search(single_pattern, salary_clean)
        if smatch:
            val = float(smatch.group(1))
            unit = smatch.group(2)
            if unit == "年":
                val = val * 10 / 12
                unit = "月"
            return val, val, unit
        return None, None, "unknown"

    low, high, unit = match.groups()
    low, high = float(low), float(high)
    if unit == "年":
        low = low * 10 / 12
        high = high * 10 / 12
        unit = "月"
    return low, high, unit

# ----------------------------
# 4. 学历等级映射
# ----------------------------
def edu_to_level(edu_str: str) -> int:
    edu_str = edu_str.strip()
    if any(kw in edu_str for kw in ["博士"]):
        return 3
    elif any(kw in edu_str for kw in ["硕士", "研究生", "硕士以上", "研究生以上"]):
        return 2
    elif "本科" in edu_str:
        return 1
    else:
        return 0

# ----------------------------
# 5. 生成用于 embedding 的文本
# ----------------------------
def extract_company_from_title(title: str) -> str:
    match = re.search(r'【[^】]+】([^，,]+)', title)
    if match:
        return match.group(1).strip()
    return "未知公司"

def build_embedding_text(title: str, job_name: str, job_salary: str, job_edu: str) -> str:
    company = extract_company_from_title(title)
    return f"岗位：{job_name}；公司：{company}；薪资：{job_salary}；学历要求：{job_edu}"

# ----------------------------
# 6. 模拟 embedding（实际应替换为真实模型）
# ----------------------------
def generate_dummy_embedding(text: str, dim: int = 768) -> List[float]:
    return [random.random() for _ in range(dim)]

# 3、定义文本embedding处理函数
def generate_real_embedding(text):
    return (
        openai_client.embeddings.create(input=text, model="text-embedding-v3")
        .data[0]
        .embedding
    )


# ----------------------------
# 7. 数据预处理与插入
# ----------------------------
def preprocess_and_insert(
    raw_data: List[Dict],
    collection: Collection,
    embedding_dim: int = 768
):
    ## 将entities定义为一个数组，数组的每个元素代表一个数据项
    entities = []


    for item in raw_data:
        title = item["title"]
        for job in item["jobDetails"]:
            job_name = job["jobName"]
            job_salary = job["jobSalary"]
            job_edu = job["jobEdu"]
            job_url = job["jobUrl"]

            min_sal, max_sal, unit = parse_salary(job_salary)
            if min_sal is None:
                min_sal = -1.0
                max_sal = -1.0

            edu_lvl = edu_to_level(job_edu)
            embed_text = build_embedding_text(title, job_name, job_salary, job_edu)
            embed_vec = generate_real_embedding(embed_text)

            entities.append(
                {
                    "title": title,
                    "job_name": job_name,
                    "job_salary": job_salary,
                    "salary_min": min_sal,
                    "salary_max": max_sal,
                    "salary_unit": unit,
                    "job_edu": job_edu,
                    "job_url": job_url,
                    "edu_level": edu_lvl,
                    "text_for_embedding": embed_text,
                    "embedding": embed_vec
                }
            )

    # 修复：确保 entities 是正确格式
    try:
        collection.insert(entities)
        collection.flush()
        print(f"✅ Inserted {len(entities)} job records into Milvus")
    except Exception as e:
        print(f"❌ Insertion failed: {e}")
        raise

# ----------------------------
# 8. 从文件读取 JSON 数据
# ----------------------------
def load_json_data(file_path: str = "jobs.json") -> List[Dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"✅ Loaded {len(data)} job postings from '{file_path}'")
        return data
    except FileNotFoundError:
        print(f"❌ File '{file_path}' not found!")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in '{file_path}': {e}")
        raise

# ----------------------------
# 9. 主程序
# ----------------------------
if __name__ == "__main__":
    JOBS_FILE = "jobs.json"          # ← 从这里读取
    COLLECTION_NAME = "job_postings"
    EMBEDDING_DIM = 1024

    # 1. 读取数据
    raw_data = load_json_data(JOBS_FILE)

    # 2. 连接并创建 collection
    connect_milvus()
    collection = create_collection(COLLECTION_NAME, EMBEDDING_DIM)

    # 3. 预处理并插入
    preprocess_and_insert(raw_data, collection, EMBEDDING_DIM)

    # 4. 验证
    print(f"📊 Total entities in collection: {collection.num_entities}")