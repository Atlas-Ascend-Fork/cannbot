# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
# First published in CAKE2 on 2026-03-24 as the ascendc-docs-search skill,
# renamed to cake-docs-search here; third-party repositories carry downstream
# copies of the same content.

"""Ascend社区文档搜索技能 - 提供Ascend社区文档搜索功能"""
import base64
import logging
from urllib.parse import urljoin, quote

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_search_args(keyword, page_num, page_size):
    """校验搜索参数；合法时返回 None，否则返回错误说明。"""
    min_page_num, max_page_num = 1, 100
    min_page_size, max_page_size = 1, 10
    if not keyword or not keyword.strip():
        return "关键词参数是必需的"
    if page_num < min_page_num or page_num > max_page_num:
        return "页码必须在1到100之间"
    if page_size < min_page_size or page_size > max_page_size:
        return "页面大小必须在1到10之间"
    return None


def _format_document(item: dict) -> dict:
    """单条搜索结果的字段映射。"""
    return {
        "title": item.get("docTitle", ""),
        "summary": item.get("docContent", ""),
        "url": item.get("docUrl", ""),
        "version": item.get("version", ""),
        "publishTime": item.get("publishTime", "")
    }


class AscendSearchSkill:
    """Ascend社区搜索技能主类"""

    def __init__(self, base_url="https://www.hiascend.com"):
        self.base_url = base_url
        self.search_endpoint = "/ascendgateway/ascendservice/content/search"
        self.headers = {
            "x-request-type": "machine",
            "Content-Type": "application/json",
            "Referer": base_url,
            "User-Agent": "Mozilla/5.0 (compatible; AscendSearchSkill/1.0)"
        }

    @staticmethod
    def _error_response(message):
        """创建标准错误响应"""
        return {"success": False, "message": message, "data": []}

    def search_documents(self,
                         keyword,
                         *,
                         lang="zh",
                         doc_type="DOC",
                         page_num=1,
                         page_size=10,
                         sort=1,
                         ignore_correction=False,
                         search_type=True):
        """搜索Ascend社区文档"""
        invalid = _validate_search_args(keyword, page_num, page_size)
        if invalid:
            return self._error_response(invalid)

        params = {
            "keyword": quote(base64.b64encode(keyword.strip().encode('utf-8')).decode('utf-8')),
            "lang": lang,
            "type": doc_type,
            "pageNum": page_num,
            "pageSize": page_size,
            "sort": sort,
            "ignoreCorrection": str(ignore_correction).lower(),
            "searchType": str(search_type).lower()
        }

        try:
            full_url = urljoin(self.base_url, self.search_endpoint)
            response = requests.get(full_url,
                                    params=params,
                                    headers=self.headers,
                                    timeout=10)
            response.raise_for_status()
            result_data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error("API请求失败", exc_info=True)
            return self._error_response(f"API请求失败: {str(e)}")
        return self._format_search_result(result_data)

    def _format_search_result(self, result_data):
        """把接口返回整理成统一结构；结构不符合预期时原样返回。"""
        is_success = result_data.get("success")
        has_data = "data" in result_data
        if not (is_success and has_data):
            return result_data

        data_content = result_data["data"]
        is_data_dict = isinstance(data_content, dict)
        has_nested_data = "data" in data_content
        if not (is_data_dict and has_nested_data):
            return result_data

        document_data = data_content["data"]
        if not isinstance(document_data, list):
            return result_data

        formatted_data = self._transform_urls([_format_document(i) for i in document_data])
        return {
            "success": True,
            "message": result_data.get("msg", "success"),
            "data": formatted_data
        }

    def _transform_urls(self, data):
        """将内部URL转换为公共URL"""
        transformed_data = []
        source_prefix = "/source/"
        document_prefix = "/document/detail/"

        for item in data:
            has_url = "url" in item and item["url"]
            if has_url:
                transformed_url = item["url"].replace(source_prefix,
                                                      document_prefix)
                is_relative_url = transformed_url.startswith("/")
                if is_relative_url:
                    transformed_url = urljoin(self.base_url, transformed_url)
                item["url"] = transformed_url

            transformed_data.append(item)

        return transformed_data
