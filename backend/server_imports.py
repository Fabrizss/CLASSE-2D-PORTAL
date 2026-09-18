from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import jwt
import bcrypt
import resend
import requests
import asyncpg
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header, Query, Response
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pywebpush import webpush, WebPushException
from .llm_chat import LlmChat, UserMessage
from google import genai
from google.genai import types as genai_types
from pypdf import PdfReader
import io
