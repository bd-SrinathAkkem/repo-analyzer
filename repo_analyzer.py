#!/usr/bin/env python3
"""
Universal AI-Powered Repository Analyzer

A production-grade tool for analyzing GitHub repositories using various AI models
to generate comprehensive build commands, development workflows, and architectural insights.

This tool supports multiple AI providers (Claude, GPT, Gemini), handles monorepos,
multi-language projects, and provides detailed analysis of project structure and
build processes.

Author: SrinathAkkem/Black Duck Software
Version: 1.0.0
License: MIT License
Created: 2024
Last Modified: 2024

Repository: https://github.com/SrinathAkkem/repo-analyzer
Documentation: https://docs.example.com/repo-analyzer

Dependencies:
    - requests>=2.31.0
    - openai>=1.0.0
    - toml>=0.10.2
    - PyYAML>=6.0
    - pathlib (built-in)

Environment Variables Required:
    - GITHUB_TOKEN: GitHub Personal Access Token (recommended)
    - AI_API_KEY: Single API key used for all AI providers

Usage:
    python repo_analyzer.py <github_repo_url> [model] [config_file]
    
    Examples:
        python repo_analyzer.py https://github.com/owner/repo
        python repo_analyzer.py https://github.com/owner/repo claude-sonnet
        python repo_analyzer.py https://github.com/owner/repo gpt-4 config.toml

License:
    MIT License
    
    Copyright (c) 2024 SrinathAkkem/Black Duck Software
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

import requests
import json
import sys
import os
import base64
import toml
import yaml
import logging
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime
from urllib.parse import urlparse
import openai

# Version information
__version__ = "1.0.0"
__author__ = "SrinathAkkem/Black Duck Software"
__email__ = "reddyakkem@blackduck.com"
__license__ = "MIT"

# Centralized constants for all hardcoded values
class Constants:
    """
    Centralized configuration constants for the repository analyzer.
    
    This class contains all hardcoded values used throughout the application,
    making it easy to modify behavior without changing code in multiple places.
    """
    
    # Application metadata
    APP_NAME = "Universal AI-Powered Repository Analyzer"
    APP_VERSION = __version__
    
    # Logging configuration
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE_PREFIX = 'repo_analyzer_'
    TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'
    MAX_LOG_FILE_SIZE_MB = 50  # Maximum log file size in MB
    
    # GitHub API configuration
    GITHUB_TOKEN_ENV = 'GITHUB_TOKEN'
    GITHUB_API_BASE = 'https://api.github.com/repos'
    GITHUB_TREE_ENDPOINT = '/git/trees/HEAD?recursive=1'
    GITHUB_CONTENTS_ENDPOINT = '/contents'
    GITHUB_API_TIMEOUT = 30  # Timeout for GitHub API calls in seconds
    GITHUB_RATE_LIMIT_BUFFER = 10  # Buffer for rate limit (requests remaining)
    
    # AI API configuration - Single key for all providers
    AI_API_KEY_ENV = 'AI_API_KEY'

    BASE_URL = 'https://llm.labs.blackduck.com'
    API_BASE_URLS = {
        'claude': BASE_URL,
        'gpt': BASE_URL,
        'gemini': BASE_URL
    }
    API_BASE_URL_ENV_PREFIX = '_API_BASE_URL'
    MODEL_NAME_MAP = {
        'claude-sonnet': 'anthropic.claude-3-7-sonnet-20250219-v1:0',
        'claude-opus': 'anthropic.claude-opus-4-20250514-v1:0',
        'claude-haiku': 'anthropic.claude-3-5-haiku-20241022-v1:0',
        'gpt-4': 'gpt-4',
        'gpt-4-turbo': 'gpt-4',
        'gpt-3.5': 'gpt-35-turbo',
        'gemini': 'vertex_ai/gemini-pro',
        'gemini-pro': 'vertex_ai/gemini-pro'
    }
    DEFAULT_MODEL = 'claude-sonnet'
    AI_TEMPERATURE = 0.2
    AI_MAX_TOKENS = 4000
    AI_MAX_RETRIES = 3
    AI_RETRY_DELAY = 2  # Base delay between retries in seconds
    AI_REQUEST_TIMEOUT = 60  # Timeout for AI API calls in seconds
    
    # File processing limits
    DEFAULT_MAX_FILES_TO_ANALYZE = 50
    DEFAULT_MAX_FILE_SIZE = 10000  # Characters, not bytes
    MAX_FILES_IN_PROMPT = 200
    MAX_TOTAL_CONTENT_SIZE = 100000  # Maximum total content size for AI analysis
    
    # Default configuration values
    DEFAULT_CONFIG = {
        'analysis_depth': 'comprehensive',
        'max_files_to_analyze': DEFAULT_MAX_FILES_TO_ANALYZE,
        'max_file_size': DEFAULT_MAX_FILE_SIZE,
        'include_source_files': True,
        'custom_prompt_template': None,
        'output_format': 'detailed',
        'command_categories': [
            'setup', 'install', 'build', 'test', 'dev', 'production',
            'deployment', 'database', 'docker', 'ci_cd', 'maintenance'
        ],
        'api_base_urls': {},
        'excluded_directories': [
            'node_modules', '.git', '__pycache__', 'dist', 'build',
            'target', '.idea', '.vscode', 'coverage', '.nyc_output'
        ],
        'excluded_file_extensions': [
            '.log', '.tmp', '.cache', '.lock', '.map', '.min.js', '.min.css'
        ]
    }
    
    # File selection patterns for fallback (ordered by priority)
    PRIORITY_PATTERNS = [
        # Package managers and build files
        'package.json', 'pom.xml', 'build.gradle', 'Cargo.toml', 'go.mod',
        'requirements.txt', 'setup.py', 'pyproject.toml', 'composer.json',
        'Gemfile', 'mix.exs', 'project.clj', 'deps.edn',
        
        # Configuration files
        'tsconfig.json', 'webpack.config.js', 'vite.config.js', 'rollup.config.js',
        'babel.config.js', 'jest.config.js', 'cypress.json',
        
        # CI/CD and deployment
        'Dockerfile', '.github/workflows', '.gitlab-ci.yml', 'Jenkinsfile',
        'docker-compose.yml', 'k8s.yml', 'kubernetes.yml',
        
        # Documentation and configuration
        'README.md', 'CONTRIBUTING.md', '.env.example', 'makefile', 'Makefile'
    ]
    
    # Supported file extensions for content analysis
    SUPPORTED_EXTENSIONS = {
        '.js', '.ts', '.jsx', '.tsx', '.py', '.java', '.go', '.rs', '.rb',
        '.php', '.cpp', '.c', '.cs', '.swift', '.kt', '.scala', '.clj',
        '.json', '.yaml', '.yml', '.toml', '.xml', '.md', '.txt', '.sh',
        '.dockerfile', '.makefile'
    }

# Initialize logging with proper configuration
def setup_logging() -> str:
    """
    Set up logging configuration with both console and file handlers.
    
    Returns:
        str: Path to the log file created
        
    Note:
        Creates timestamped log files to avoid conflicts in concurrent runs.
    """
    timestamp = datetime.now().strftime(Constants.TIMESTAMP_FORMAT)
    log_filename = f"{Constants.LOG_FILE_PREFIX}{timestamp}.log"
    
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / log_filename
    
    # Configure logging with detailed format
    logging.basicConfig(
        level=getattr(logging, Constants.LOG_LEVEL),
        format=Constants.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),  # Console output
            logging.FileHandler(log_path, encoding='utf-8')  # File output
        ]
    )
    
    # Set third-party library log levels to reduce noise
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    
    return str(log_path)

# Initialize logger
log_file_path = setup_logging()
logger = logging.getLogger(__name__)

class RepositoryAnalyzerError(Exception):
    """Base exception class for repository analyzer errors."""
    pass

class GitHubAPIError(RepositoryAnalyzerError):
    """Exception raised for GitHub API related errors."""
    pass

class AIModelError(RepositoryAnalyzerError):
    """Exception raised for AI model related errors."""
    pass

class ConfigurationError(RepositoryAnalyzerError):
    """Exception raised for configuration related errors."""
    pass

class UniversalRepoAnalyzer:
    """
    Universal Repository Analyzer using AI for comprehensive project analysis.
    
    This class provides functionality to:
    1. Fetch repository structure and content from GitHub
    2. Analyze project architecture using AI models
    3. Generate build commands and development workflows
    4. Handle various project types including monorepos and multi-language projects
    
    Attributes:
        github_token (str): GitHub API token for authentication
        model (str): AI model identifier (e.g., 'claude-sonnet', 'gpt-4')
        config (Dict[str, Any]): Configuration dictionary
        api_key (str): API key for the selected AI model
        base_url (str): Base URL for AI API calls
        client (OpenAI): OpenAI-compatible client for AI API calls
        
    Raises:
        ConfigurationError: When required configuration is missing or invalid
        GitHubAPIError: When GitHub API calls fail
        AIModelError: When AI model calls fail
    """

    def __init__(self, model: str = Constants.DEFAULT_MODEL, config_file: Optional[str] = None):
        """
        Initialize the analyzer with model and optional configuration file.

        Args:
            model (str): AI model to use (e.g., 'claude-sonnet', 'gpt-4', 'gemini')
            config_file (str, optional): Path to configuration file (TOML, YAML, or JSON)
            
        Raises:
            ConfigurationError: If API client initialization fails or required keys are missing
            
        Example:
            >>> analyzer = UniversalRepoAnalyzer('claude-sonnet', 'config.toml')
            >>> context = analyzer.get_full_repository_context('https://github.com/owner/repo')
        """
        logger.info(f"Initializing {Constants.APP_NAME} v{Constants.APP_VERSION}")
        logger.info(f"Log file: {log_file_path}")
        
        # Validate and normalize model name
        self.model = self._normalize_model_name(model)
        logger.info(f"Using AI model: {self.model}")
        
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Setup GitHub authentication
        self.github_token = os.getenv(Constants.GITHUB_TOKEN_ENV)
        if not self.github_token:
            logger.warning(
                f"{Constants.GITHUB_TOKEN_ENV} not set. "
                "GitHub API rate limits will apply (60 requests/hour vs 5000/hour authenticated)"
            )
        
        # Setup AI client
        try:
            self.api_key = self._get_api_key_for_model()
            self.base_url = self._get_base_url_for_model()
            
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"Initialized AI client for {self.model} with base_url: {self.base_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            raise ConfigurationError(f"Cannot initialize AI client for {self.model}: {e}")

    def _normalize_model_name(self, model: str) -> str:
        """
        Normalize and validate the model name.
        
        Args:
            model (str): Raw model name from user input
            
        Returns:
            str: Normalized model name
            
        Raises:
            ConfigurationError: If model name is not supported
        """
        normalized = model.lower().strip()
        
        # Check if it's a valid model
        if normalized not in Constants.MODEL_NAME_MAP:
            available_models = list(Constants.MODEL_NAME_MAP.keys())
            logger.error(f"Unsupported model '{model}'. Available models: {available_models}")
            raise ConfigurationError(f"Unsupported model '{model}'. Available: {available_models}")
        
        return normalized

    def _get_api_key_for_model(self) -> str:
        """
        Get the universal AI API key from environment variable.

        Returns:
            str: AI API key for all providers

        Raises:
            ConfigurationError: If the AI API key is not set

        Note:
            Uses a single AI_API_KEY environment variable for all AI providers.
            This simplifies configuration while supporting all models.
        """
        api_key = os.getenv(Constants.AI_API_KEY_ENV)

        if not api_key:
            logger.error(f"Required environment variable {Constants.AI_API_KEY_ENV} not set")
            raise ConfigurationError(
                f"{Constants.AI_API_KEY_ENV} not set in environment. "
                f"Please set this environment variable with your API key. "
                f"This single key will be used for all AI models ({self.model})."
            )

        # Validate API key format (basic check)
        if len(api_key.strip()) < 10:
            logger.warning(f"API key seems too short. Please verify your {Constants.AI_API_KEY_ENV}.")

        return api_key

    def _get_base_url_for_model(self) -> str:
        """
        Get the base URL for API calls, checking config, environment, then defaults.

        Returns:
            str: Base URL for the selected model

        Note:
            Priority order:
            1. Configuration file setting for 'base_url'
            2. Environment variable AI_API_BASE_URL
            3. Default hardcoded URL (same for all models)
        """
        # Check configuration file first
        config_urls = self.config.get('api_base_urls', {})
        if 'base_url' in config_urls:
            logger.info(f"Using base URL from config: {config_urls['base_url']}")
            return config_urls['base_url']

        # Check environment variable
        env_url = os.getenv('AI_API_BASE_URL')
        if env_url:
            logger.info(f"Using base URL from environment AI_API_BASE_URL: {env_url}")
            return env_url

        # Use default (same for all models)
        default_url = Constants.BASE_URL
        logger.info(f"Using default base URL: {default_url}")
        return default_url

    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """
        Load configuration from file or use defaults. Supports TOML, YAML, and JSON.

        Args:
            config_file (str, optional): Path to configuration file
            
        Returns:
            Dict[str, Any]: Configuration dictionary with defaults applied
            
        Note:
            Configuration file format is auto-detected based on file extension:
            - .toml -> TOML format
            - .yml/.yaml -> YAML format  
            - .json -> JSON format
            
            If loading fails, defaults are used and a warning is logged.
        """
        config = Constants.DEFAULT_CONFIG.copy()

        if not config_file:
            logger.info("No configuration file specified, using defaults")
            return config

        config_path = Path(config_file)
        if not config_path.exists():
            logger.warning(f"Configuration file {config_file} not found, using defaults")
            return config

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_extension = config_path.suffix.lower()
                
                if file_extension == '.toml':
                    user_config = toml.load(f)
                elif file_extension in ['.yml', '.yaml']:
                    user_config = yaml.safe_load(f)
                elif file_extension == '.json':
                    user_config = json.load(f)
                else:
                    # Try to auto-detect format by content
                    content = f.read()
                    f.seek(0)
                    
                    if content.strip().startswith('{'):
                        user_config = json.load(f)
                    elif '=' in content and '[' in content:
                        f.seek(0)
                        user_config = toml.load(f)
                    else:
                        f.seek(0)
                        user_config = yaml.safe_load(f)
                
                # Merge user config with defaults
                config.update(user_config)
                logger.info(f"Successfully loaded configuration from {config_file}")
                
                # Validate critical config values
                self._validate_config(config)
                
        except Exception as e:
            logger.error(f"Failed to load configuration file {config_file}: {e}")
            logger.info("Continuing with default configuration")

        return config

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration values and apply reasonable limits.
        
        Args:
            config (Dict[str, Any]): Configuration dictionary to validate
            
        Note:
            Modifies config in-place to ensure values are within reasonable bounds.
        """
        # Ensure numeric values are within reasonable bounds
        if config.get('max_files_to_analyze', 0) > 200:
            logger.warning("max_files_to_analyze too high, capping at 200")
            config['max_files_to_analyze'] = 200
        
        if config.get('max_file_size', 0) > 50000:
            logger.warning("max_file_size too high, capping at 50000 characters")
            config['max_file_size'] = 50000
        
        # Ensure required lists exist
        if not isinstance(config.get('command_categories'), list):
            config['command_categories'] = Constants.DEFAULT_CONFIG['command_categories']
        
        if not isinstance(config.get('excluded_directories'), list):
            config['excluded_directories'] = Constants.DEFAULT_CONFIG['excluded_directories']

    def _parse_github_url(self, repo_url: str) -> Tuple[str, str]:
        """
        Parse GitHub repository URL to extract owner and repository name.
        
        Args:
            repo_url (str): GitHub repository URL
            
        Returns:
            Tuple[str, str]: (owner, repository_name)
            
        Raises:
            ValueError: If URL format is invalid
            
        Example:
            >>> owner, repo = self._parse_github_url('https://github.com/owner/repo.git')
            >>> print(f"{owner}/{repo}")  # outputs: owner/repo
        """
        try:
            # Handle various GitHub URL formats
            url = repo_url.strip()
            
            # Remove common prefixes and suffixes
            url = url.replace('https://github.com/', '')
            url = url.replace('http://github.com/', '')
            url = url.replace('git@github.com:', '')
            url = url.replace('.git', '')
            url = url.rstrip('/')
            
            # Split and validate
            parts = url.split('/')
            if len(parts) != 2:
                raise ValueError(f"Expected format: owner/repo, got: {url}")
            
            owner, repo = parts[0], parts[1]
            
            # Basic validation
            if not owner or not repo:
                raise ValueError("Owner and repository name cannot be empty")
            
            # GitHub username/repo name validation (basic)
            if not re.match(r'^[a-zA-Z0-9._-]+$', owner):
                raise ValueError(f"Invalid owner name: {owner}")
            if not re.match(r'^[a-zA-Z0-9._-]+$', repo):
                raise ValueError(f"Invalid repository name: {repo}")
            
            logger.debug(f"Parsed GitHub URL: {owner}/{repo}")
            return owner, repo
            
        except Exception as e:
            logger.error(f"Failed to parse GitHub URL '{repo_url}': {e}")
            raise ValueError(f"Invalid GitHub URL format: {repo_url}. Expected: https://github.com/owner/repo")

    def get_full_repository_context(self, repo_url: str) -> Dict[str, Any]:
        """
        Fetch comprehensive repository context using AI-driven discovery.

        This method orchestrates the complete repository analysis process:
        1. Fetches repository metadata from GitHub API
        2. Retrieves complete file tree structure
        3. Uses AI to select important files for analysis
        4. Downloads content of selected files
        5. Performs AI-driven structure analysis

        Args:
            repo_url (str): GitHub repository URL
            
        Returns:
            Dict[str, Any]: Repository context dictionary containing:
                - owner (str): Repository owner
                - repo (str): Repository name  
                - metadata (Dict): Repository metadata from GitHub API
                - all_files (List[str]): Complete list of file paths
                - structure (Dict): AI-generated structure analysis
                - file_contents (Dict[str, str]): Content of analyzed files
                - total_files (int): Total number of files in repository
                - analyzed_files (int): Number of files actually analyzed
                - error (str): Error message if analysis failed
                
        Note:
            If any step fails, returns a dictionary with an 'error' key
            containing the error message.
        """
        try:
            # Parse and validate GitHub URL
            owner, repo = self._parse_github_url(repo_url)
            logger.info(f"Starting analysis for {owner}/{repo}")
            
            # Setup request headers for GitHub API
            headers = self._get_github_headers()
            
            # Step 1: Fetch repository metadata
            logger.info("Fetching repository metadata...")
            repo_info = self._fetch_repo_info(owner, repo, headers)
            if not repo_info:
                raise GitHubAPIError("Failed to fetch repository metadata")
            
            # Step 2: Fetch complete file tree
            logger.info("Fetching complete file tree...")
            all_files = self._fetch_complete_file_tree(owner, repo, headers)
            if not all_files:
                raise GitHubAPIError("Failed to fetch repository file tree")
            
            # Filter out excluded files and directories
            filtered_files = self._filter_files(all_files)
            logger.info(f"Filtered {len(all_files)} files to {len(filtered_files)} relevant files")
            
            # Step 3: AI-driven file selection for detailed analysis
            logger.info("Using AI to select important files for analysis...")
            important_files = self._ai_select_files_to_analyze(filtered_files, repo_info)
            
            # Step 4: Fetch content of selected files
            logger.info(f"Fetching content for {len(important_files)} selected files...")
            file_contents = self._fetch_file_contents(owner, repo, important_files, headers)
            
            # Step 5: AI-driven structure analysis
            logger.info("Performing AI-driven structure analysis...")
            structure_analysis = self._ai_analyze_repo_structure(filtered_files, repo_info)

            # Compile comprehensive context
            context = {
                'owner': owner,
                'repo': repo,
                'metadata': repo_info,
                'all_files': filtered_files,
                'structure': structure_analysis,
                'file_contents': file_contents,
                'total_files': len(filtered_files),
                'analyzed_files': len(file_contents),
                'analysis_timestamp': datetime.now().isoformat(),
                'analyzer_version': Constants.APP_VERSION
            }
            
            logger.info(
                f"Repository context successfully compiled: "
                f"{context['total_files']} total files, "
                f"{context['analyzed_files']} analyzed in detail"
            )
            
            return context

        except Exception as e:
            error_msg = f"Error fetching repository context: {e}"
            logger.error(error_msg)
            return {
                'error': error_msg,
                'error_type': type(e).__name__,
                'repo_url': repo_url,
                'timestamp': datetime.now().isoformat()
            }

    def _get_github_headers(self) -> Dict[str, str]:
        """
        Get headers for GitHub API requests including authentication if available.
        
        Returns:
            Dict[str, str]: HTTP headers for GitHub API requests
        """
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'{Constants.APP_NAME}/{Constants.APP_VERSION}'
        }
        
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
            
        return headers

    def _filter_files(self, all_files: List[str]) -> List[str]:
        """
        Filter files to exclude irrelevant directories and file types.
        
        Args:
            all_files (List[str]): Complete list of file paths
            
        Returns:
            List[str]: Filtered list of relevant file paths
        """
        filtered = []
        excluded_dirs = self.config.get('excluded_directories', [])
        excluded_extensions = self.config.get('excluded_file_extensions', [])
        
        for file_path in all_files:
            # Skip files in excluded directories
            if any(excluded_dir in file_path.split('/') for excluded_dir in excluded_dirs):
                continue
            
            # Skip files with excluded extensions
            if any(file_path.endswith(ext) for ext in excluded_extensions):
                continue
            
            # Only include files with supported extensions or no extension
            file_ext = Path(file_path).suffix.lower()
            if file_ext and file_ext not in Constants.SUPPORTED_EXTENSIONS:
                continue
                
            filtered.append(file_path)
        
        return filtered

    def _fetch_repo_info(self, owner: str, repo: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Fetch repository metadata from GitHub API with error handling and rate limiting.

        Args:
            owner (str): Repository owner username
            repo (str): Repository name
            headers (Dict[str, str]): HTTP headers for authentication
            
        Returns:
            Dict[str, Any]: Repository metadata or empty dict on failure
            
        Raises:
            GitHubAPIError: If API request fails after retries
        """
        url = f"{Constants.GITHUB_API_BASE}/{owner}/{repo}"
        
        for attempt in range(3):  # Retry up to 3 times
            try:
                logger.debug(f"Fetching repository info (attempt {attempt + 1}): {url}")
                
                response = requests.get(
                    url, 
                    headers=headers, 
                    timeout=Constants.GITHUB_API_TIMEOUT
                )
                
                # Handle rate limiting
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    reset_time = response.headers.get('X-RateLimit-Reset')
                    if reset_time:
                        reset_datetime = datetime.fromtimestamp(int(reset_time))
                        logger.warning(f"GitHub rate limit exceeded. Resets at {reset_datetime}")
                    raise GitHubAPIError("GitHub API rate limit exceeded")
                
                response.raise_for_status()
                repo_data = response.json()
                
                # Log rate limit status
                remaining = response.headers.get('X-RateLimit-Remaining')
                if remaining:
                    logger.debug(f"GitHub API requests remaining: {remaining}")
                
                return repo_data
                
            except requests.exceptions.Timeout:
                logger.warning(f"GitHub API timeout (attempt {attempt + 1})")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"GitHub API request failed (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise GitHubAPIError(f"Failed to fetch repository info: {e}")
        
        return {}

    def _fetch_complete_file_tree(self, owner: str, repo: str, headers: Dict[str, str]) -> List[str]:
        """
        Fetch complete file tree recursively from GitHub API with error handling.

        Args:
            owner (str): Repository owner username
            repo (str): Repository name  
            headers (Dict[str, str]): HTTP headers for authentication
            
        Returns:
            List[str]: List of file paths or empty list on failure
            
        Note:
            Uses GitHub's recursive tree API which is more efficient than
            making multiple API calls for directory traversal.
        """
        url = f"{Constants.GITHUB_API_BASE}/{owner}/{repo}{Constants.GITHUB_TREE_ENDPOINT}"
        
        for attempt in range(3):
            try:
                logger.debug(f"Fetching file tree (attempt {attempt + 1}): {url}")
                
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=Constants.GITHUB_API_TIMEOUT
                )
                
                # Handle rate limiting
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    raise GitHubAPIError("GitHub API rate limit exceeded")
                
                response.raise_for_status()
                tree_data = response.json()
                
                # Extract file paths (blobs only, not trees/directories)
                file_paths = [
                    item['path'] 
                    for item in tree_data.get('tree', []) 
                    if item['type'] == 'blob'
                ]
                
                logger.info(f"Retrieved {len(file_paths)} files from repository tree")
                return file_paths
                
            except requests.exceptions.Timeout:
                logger.warning(f"File tree fetch timeout (attempt {attempt + 1})")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch file tree (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise GitHubAPIError(f"Failed to fetch file tree: {e}")
        
        return []

    def _ai_select_files_to_analyze(self, all_files: List[str], repo_info: Dict[str, Any]) -> List[str]:
        """
        Use AI to intelligently select the most important files for detailed analysis.
        
        Falls back to heuristic selection if AI call fails.

        Args:
            all_files (List[str]): Complete list of file paths in repository
            repo_info (Dict[str, Any]): Repository metadata from GitHub API
            
        Returns:
            List[str]: List of selected file paths for detailed analysis
            
        Note:
            AI selection considers:
            - Build and configuration files
            - CI/CD workflows  
            - Key source files indicating architecture
            - Monorepo detection and handling
            - Multi-language project support
        """
        # Limit files shown to AI to prevent prompt overflow
        files_sample = all_files[:Constants.MAX_FILES_IN_PROMPT]
        files_list = "\n".join(f"- {f}" for f in files_sample)
        
        # Prepare additional context
        topics = repo_info.get('topics', [])
        topics_str = ", ".join(topics) if topics else "None specified"
        
        selection_prompt = f"""
You are an expert software engineer analyzing a repository to identify the most crucial files for understanding its build system, architecture, and development workflow.

REPOSITORY CONTEXT:
Name: {repo_info.get('name', 'Unknown')}
Description: {repo_info.get('description', 'No description provided')}
Primary Language: {repo_info.get('language', 'Not specified')}
Topics/Tags: {topics_str}
Size: {repo_info.get('size', 0)} KB
Stars: {repo_info.get('stargazers_count', 0)}
Forks: {repo_info.get('forks_count', 0)}
Total Files Available: {len(all_files)}

FILES TO ANALYZE (showing first {len(files_sample)} of {len(all_files)}):
{files_list}

SELECTION CRITERIA:
Select exactly {self.config['max_files_to_analyze']} files that are most important for:
1. Understanding build processes and dependencies
2. Identifying project structure and architecture
3. Recognizing CI/CD workflows and deployment
4. Detecting monorepo patterns or multi-language setups
5. Key configuration and documentation files

PRIORITIZE:
- Package managers: package.json, pom.xml, Cargo.toml, go.mod, requirements.txt, etc.
- Build tools: webpack.config.js, vite.config.js, tsconfig.json, Makefile, etc.
- CI/CD: .github/workflows/*, .gitlab-ci.yml, Jenkinsfile, etc.
- Containerization: Dockerfile, docker-compose.yml, k8s manifests
- Documentation: README.md, CONTRIBUTING.md, docs with setup info
- Root configuration files over nested ones (unless monorepo detected)

MONOREPO DETECTION:
If you detect monorepo patterns (multiple package.json files, lerna.json, nx.json, etc.),
include key files from different packages/workspaces.

OUTPUT FORMAT:
Return ONLY a valid JSON array of file paths, no additional text:
["path/to/file1", "path/to/file2", "path/to/file3", ...]

Ensure all selected files exist in the provided list above.
"""

        try:
            logger.debug("Requesting AI file selection...")
            ai_response = self._call_ai_model(selection_prompt)
            
            if isinstance(ai_response, str):
                # Extract JSON array from response
                start_idx = ai_response.find('[')
                end_idx = ai_response.rfind(']') + 1
                
                if start_idx != -1 and end_idx > 0:
                    json_str = ai_response[start_idx:end_idx]
                    selected_files = json.loads(json_str)
                    
                    # Validate that selected files exist in our file list
                    valid_selected = [
                        f for f in selected_files 
                        if isinstance(f, str) and f in all_files
                    ]
                    
                    if valid_selected:
                        logger.info(f"AI selected {len(valid_selected)} files for analysis")
                        return valid_selected[:self.config['max_files_to_analyze']]
                    else:
                        logger.warning("AI selected no valid files, falling back to heuristic")
                        
        except json.JSONDecodeError as e:
            logger.warning(f"AI file selection returned invalid JSON: {e}")
        except Exception as e:
            logger.warning(f"AI file selection failed: {e}")

        # Fallback: Heuristic selection using priority patterns
        logger.info("Using heuristic file selection as fallback")
        return self._heuristic_file_selection(all_files)

    def _heuristic_file_selection(self, all_files: List[str]) -> List[str]:
        """
        Fallback heuristic method for selecting important files when AI selection fails.
        
        Args:
            all_files (List[str]): Complete list of file paths
            
        Returns:
            List[str]: Heuristically selected file paths
            
        Note:
            Uses priority patterns and scoring to select the most likely
            important files for repository analysis.
        """
        scored_files = []
        
        for file_path in all_files:
            score = 0
            file_name = os.path.basename(file_path).lower()
            
            # Score based on priority patterns
            for i, pattern in enumerate(Constants.PRIORITY_PATTERNS):
                if pattern.lower() in file_path.lower():
                    # Higher score for higher priority patterns
                    score += (len(Constants.PRIORITY_PATTERNS) - i) * 10
                    break
            
            # Additional scoring factors
            if file_path.count('/') == 0:  # Root level files
                score += 5
            if 'config' in file_name or 'setup' in file_name:
                score += 3
            if file_name in ['readme.md', 'license', 'contributing.md']:
                score += 2
            
            if score > 0:
                scored_files.append((file_path, score))
        
        # Sort by score and take top files
        scored_files.sort(key=lambda x: x[1], reverse=True)
        selected = [f[0] for f in scored_files[:self.config['max_files_to_analyze']]]
        
        logger.info(f"Heuristic selection chose {len(selected)} files")
        return selected

    def _fetch_file_contents(self, owner: str, repo: str, file_paths: List[str], headers: Dict[str, str]) -> Dict[str, str]:
        """
        Fetch contents of selected files with size limits, encoding handling, and error recovery.

        Args:
            owner (str): Repository owner username
            repo (str): Repository name
            file_paths (List[str]): List of file paths to fetch content for
            headers (Dict[str, str]): HTTP headers for authentication
            
        Returns:
            Dict[str, str]: Dictionary mapping file paths to their text contents
            
        Note:
            - Handles binary files by skipping them
            - Applies size limits to prevent memory issues
            - Uses proper error handling to continue on individual file failures
            - Implements rate limiting awareness
        """
        file_contents = {}
        total_content_size = 0
        max_total_size = Constants.MAX_TOTAL_CONTENT_SIZE
        
        for i, file_path in enumerate(file_paths):
            # Check if we've exceeded total content size limit
            if total_content_size >= max_total_size:
                logger.warning(f"Reached maximum total content size ({max_total_size} chars), stopping at {i+1}/{len(file_paths)} files")
                break
                
            try:
                url = f"{Constants.GITHUB_API_BASE}/{owner}/{repo}{Constants.GITHUB_CONTENTS_ENDPOINT}/{file_path}"
                logger.debug(f"Fetching content for: {file_path}")
                
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=Constants.GITHUB_API_TIMEOUT
                )
                
                # Handle rate limiting gracefully
                if response.status_code == 403 and 'rate limit' in response.text.lower():
                    logger.warning("Hit rate limit while fetching file contents")
                    break
                
                # Skip files that don't exist or are inaccessible
                if response.status_code == 404:
                    logger.debug(f"File not found (may be in submodule): {file_path}")
                    continue
                    
                response.raise_for_status()
                content_data = response.json()
                
                # Handle base64 encoded content
                if content_data.get('encoding') == 'base64':
                    try:
                        decoded_bytes = base64.b64decode(content_data['content'])
                        
                        # Try to decode as UTF-8, skip binary files
                        try:
                            decoded_text = decoded_bytes.decode('utf-8')
                        except UnicodeDecodeError:
                            logger.debug(f"Skipping binary file: {file_path}")
                            continue
                        
                        # Apply size limit per file
                        max_size = self.config['max_file_size']
                        if len(decoded_text) > max_size:
                            logger.debug(f"Truncating large file {file_path} from {len(decoded_text)} to {max_size} chars")
                            decoded_text = decoded_text[:max_size] + "\n... (truncated)"
                        
                        file_contents[file_path] = decoded_text
                        total_content_size += len(decoded_text)
                        
                    except Exception as decode_error:
                        logger.warning(f"Failed to decode content for {file_path}: {decode_error}")
                        continue
                        
                else:
                    logger.warning(f"Unexpected encoding for {file_path}: {content_data.get('encoding')}")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch content for {file_path}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Unexpected error fetching {file_path}: {e}")
                continue
        
        logger.info(f"Successfully fetched content for {len(file_contents)}/{len(file_paths)} files ({total_content_size} total chars)")
        return file_contents

    def _ai_analyze_repo_structure(self, all_files: List[str], repo_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to analyze repository structure, detecting patterns like monorepos, 
        multi-language setups, and architectural decisions.
        
        Falls back to basic analysis if AI fails.

        Args:
            all_files (List[str]): Complete list of file paths in repository
            repo_info (Dict[str, Any]): Repository metadata from GitHub API
            
        Returns:
            Dict[str, Any]: Comprehensive structure analysis dictionary
            
        Note:
            Analysis includes:
            - Directory structure and organization
            - Language detection and distribution  
            - Monorepo vs single-project identification
            - Testing, documentation, and CI/CD presence
            - Architectural patterns and frameworks
        """
        # Prepare file list for analysis (limit to prevent prompt overflow)
        files_sample = all_files[:Constants.MAX_FILES_IN_PROMPT]
        files_list = "\n".join(f"- {f}" for f in files_sample)
        
        # Prepare additional context
        topics = repo_info.get('topics', [])
        topics_str = ", ".join(topics) if topics else "None"
        
        structure_prompt = f"""
You are an expert software architect analyzing a repository's structure and organization patterns.

REPOSITORY CONTEXT:
Name: {repo_info.get('name', 'Unknown')}
Description: {repo_info.get('description', 'No description provided')}
Primary Language: {repo_info.get('language', 'Not specified')}
Topics/Tags: {topics_str}
Size: {repo_info.get('size', 0)} KB
Created: {repo_info.get('created_at', 'Unknown')}
Last Updated: {repo_info.get('updated_at', 'Unknown')}
Default Branch: {repo_info.get('default_branch', 'main')}

FILES STRUCTURE (showing {len(files_sample)} of {len(all_files)} total files):
{files_list}

ANALYSIS REQUIREMENTS:
Analyze the repository structure comprehensively, focusing on:

1. DIRECTORY ORGANIZATION: Identify main directories and their purposes
2. LANGUAGE DETECTION: All programming languages used (not just GitHub's primary)
3. PROJECT TYPE: Monorepo, single project, microservices, library, application, etc.
4. ARCHITECTURE PATTERNS: MVC, microservices, layered, modular, etc.
5. FRAMEWORKS & TOOLS: Web frameworks, build tools, testing frameworks
6. DEVELOPMENT WORKFLOW: Testing setup, CI/CD, documentation, deployment

SPECIFIC DETECTIONS:
- Monorepo indicators: multiple package.json, lerna.json, nx.json, workspaces
- Multi-language: different language files in different directories
- Testing: unit, integration, e2e test directories and files
- Documentation: README files, docs directories, wikis
- CI/CD: GitHub Actions, GitLab CI, Jenkins, etc.
- Containerization: Docker, Kubernetes, container registries
- Database: Migrations, schema files, ORM configurations

OUTPUT FORMAT:
Return ONLY a valid JSON object with this exact structure:

{{
    "directories": {{
        "main_directories": ["list of primary directories"],
        "source_directories": ["directories containing source code"],
        "config_directories": ["directories with configuration"],
        "test_directories": ["directories with tests"],
        "doc_directories": ["directories with documentation"]
    }},
    "languages": {{
        "primary_language": "main language detected",
        "secondary_languages": ["other languages found"],
        "language_distribution": {{"language": "estimated_percentage"}},
        "frameworks_detected": ["frameworks and libraries identified"]
    }},
    "project_type": {{
        "architecture": "monorepo|single-project|microservices|library|application",
        "complexity": "simple|moderate|complex|enterprise",
        "domain": "web|mobile|desktop|cli|library|api|fullstack|data|ml",
        "scale": "personal|team|enterprise|open-source"
    }},
    "features": {{
        "has_tests": boolean,
        "has_ci_cd": boolean,
        "has_documentation": boolean,
        "has_docker": boolean,
        "has_database": boolean,
        "has_api": boolean,
        "has_frontend": boolean,
        "has_backend": boolean
    }},
    "monorepo_analysis": {{
        "is_monorepo": boolean,
        "workspace_tool": "lerna|nx|rush|yarn-workspaces|npm-workspaces|none",
        "packages": ["list of package/workspace directories if monorepo"],
        "shared_dependencies": boolean
    }},
    "build_system": {{
        "build_tools": ["detected build tools"],
        "package_managers": ["npm|yarn|pip|maven|gradle|cargo|go-mod|etc"],
        "bundlers": ["webpack|rollup|vite|parcel|etc"],
        "task_runners": ["npm-scripts|gulp|grunt|make|etc"]
    }},
    "deployment": {{
        "deployment_targets": ["cloud platforms or deployment types detected"],
        "containerization": "docker|kubernetes|none",
        "infrastructure_as_code": "terraform|ansible|helm|none"
    }},
    "quality_assurance": {{
        "linting": ["eslint|pylint|golint|etc if detected"],
        "formatting": ["prettier|black|gofmt|etc if detected"],
        "testing_frameworks": ["jest|pytest|junit|etc if detected"],
        "code_coverage": boolean
    }},
    "insights": {{
        "architectural_patterns": ["patterns identified"],
        "notable_conventions": ["naming, structure, organization patterns"],
        "potential_improvements": ["suggestions based on structure analysis"],
        "estimated_team_size": "individual|small-team|large-team|enterprise",
        "maintenance_level": "active|maintained|legacy|experimental"
    }}
}}

Ensure the response is valid JSON only, with no additional text or markdown formatting.
"""

        try:
            logger.debug("Requesting AI structure analysis...")
            ai_response = self._call_ai_model(structure_prompt)
            
            if isinstance(ai_response, str):
                # Extract JSON from response
                start_idx = ai_response.find('{')
                end_idx = ai_response.rfind('}') + 1
                
                if start_idx != -1 and end_idx > 0:
                    json_str = ai_response[start_idx:end_idx]
                    structure_analysis = json.loads(json_str)
                    
                    logger.info("AI structure analysis completed successfully")
                    return structure_analysis
                    
        except json.JSONDecodeError as e:
            logger.warning(f"AI structure analysis returned invalid JSON: {e}")
        except Exception as e:
            logger.warning(f"AI structure analysis failed: {e}")

        # Fallback: Basic heuristic structure analysis
        logger.info("Using fallback heuristic structure analysis")
        return self._heuristic_structure_analysis(all_files, repo_info)

    def _heuristic_structure_analysis(self, all_files: List[str], repo_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback heuristic method for analyzing repository structure when AI fails.
        
        Args:
            all_files (List[str]): Complete list of file paths
            repo_info (Dict[str, Any]): Repository metadata
            
        Returns:
            Dict[str, Any]: Basic structure analysis
        """
        # Extract directory structure
        directories = set()
        file_extensions = {}
        
        for file_path in all_files:
            # Count directories
            dir_parts = file_path.split('/')[:-1]
            for i in range(len(dir_parts)):
                directories.add('/'.join(dir_parts[:i+1]))
            
            # Count file extensions
            if '.' in file_path:
                ext = os.path.splitext(file_path)[1].lower()
                file_extensions[ext] = file_extensions.get(ext, 0) + 1
        
        # Basic language detection
        extension_to_language = {
            '.js': 'JavaScript', '.ts': 'TypeScript', '.py': 'Python',
            '.java': 'Java', '.go': 'Go', '.rs': 'Rust', '.cpp': 'C++',
            '.c': 'C', '.cs': 'C#', '.rb': 'Ruby', '.php': 'PHP',
            '.swift': 'Swift', '.kt': 'Kotlin', '.scala': 'Scala'
        }
        
        languages_detected = []
        for ext, count in file_extensions.items():
            if ext in extension_to_language and count > 0:
                languages_detected.append(extension_to_language[ext])
        
        # Basic feature detection
        has_tests = any('test' in f.lower() or 'spec' in f.lower() for f in all_files)
        has_ci_cd = any('.github/' in f or '.gitlab-ci' in f or 'jenkinsfile' in f.lower() for f in all_files)
        has_docker = any('dockerfile' in f.lower() or 'docker-compose' in f.lower() for f in all_files)
        has_docs = any('readme' in f.lower() or 'doc' in f.lower() for f in all_files)
        
        # Monorepo detection
        package_json_count = sum(1 for f in all_files if f.endswith('package.json'))
        is_monorepo = package_json_count > 1 or any('lerna.json' in f or 'nx.json' in f for f in all_files)
        
        return {
            "directories": {
                "main_directories": sorted(list(directories))[:10],
                "source_directories": [d for d in directories if any(src in d for src in ['src', 'lib', 'app'])],
                "config_directories": [d for d in directories if any(cfg in d for cfg in ['config', 'conf', '.github'])],
                "test_directories": [d for d in directories if any(test in d for test in ['test', 'spec', '__tests__'])],
                "doc_directories": [d for d in directories if any(doc in d for doc in ['doc', 'docs', 'documentation'])]
            },
            "languages": {
                "primary_language": repo_info.get('language', 'Unknown'),
                "secondary_languages": languages_detected[:5],
                "language_distribution": {lang: "estimated" for lang in languages_detected[:3]},
                "frameworks_detected": []
            },
            "project_type": {
                "architecture": "monorepo" if is_monorepo else "single-project",
                "complexity": "moderate",
                "domain": "unknown",
                "scale": "unknown"
            },
            "features": {
                "has_tests": has_tests,
                "has_ci_cd": has_ci_cd,
                "has_documentation": has_docs,
                "has_docker": has_docker,
                "has_database": False,
                "has_api": False,
                "has_frontend": any(ext in file_extensions for ext in ['.html', '.css', '.js', '.ts']),
                "has_backend": any(ext in file_extensions for ext in ['.py', '.java', '.go', '.php'])
            },
            "monorepo_analysis": {
                "is_monorepo": is_monorepo,
                "workspace_tool": "unknown",
                "packages": [],
                "shared_dependencies": False
            },
            "build_system": {
                "build_tools": [],
                "package_managers": [],
                "bundlers": [],
                "task_runners": []
            },
            "deployment": {
                "deployment_targets": [],
                "containerization": "docker" if has_docker else "none",
                "infrastructure_as_code": "none"
            },
            "quality_assurance": {
                "linting": [],
                "formatting": [],
                "testing_frameworks": [],
                "code_coverage": False
            },
            "insights": {
                "architectural_patterns": [],
                "notable_conventions": [],
                "potential_improvements": [],
                "estimated_team_size": "unknown",
                "maintenance_level": "unknown",
                "fallback_analysis": True
            }
        }

    def _format_file_contents(self, file_contents: Dict[str, str]) -> str:
        """
        Format file contents for inclusion in AI prompts with clear delimiters and structure.

        Args:
            file_contents (Dict[str, str]): Dictionary mapping file paths to contents
            
        Returns:
            str: Formatted string with clear file boundaries and metadata
            
        Note:
            Uses consistent formatting to help AI models parse file contents:
            - Clear start/end delimiters
            - File path headers
            - Content preservation with proper encoding
        """
        if not file_contents:
            return "No file contents available for analysis."
        
        formatted_parts = []
        
        for file_path, content in file_contents.items():
            # Add file header with metadata
            file_size = len(content)
            file_ext = os.path.splitext(file_path)[1]
            
            header = f"\n{'='*60}\nFILE: {file_path}\nSIZE: {file_size} characters\nTYPE: {file_ext or 'no extension'}\n{'='*60}"
            footer = f"\n{'='*60}\nEND FILE: {file_path}\n{'='*60}\n"
            
            formatted_parts.append(f"{header}\n{content.strip()}\n{footer}")
        
        return "\n".join(formatted_parts)

    def analyze_with_ai(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform comprehensive AI analysis of the repository using custom or default prompts.

        This is the main analysis method that takes the repository context and generates
        detailed insights including build commands, development workflows, and architectural
        recommendations.

        Args:
            repo_data (Dict[str, Any]): Repository context from get_full_repository_context()
                Must contain: owner, repo, metadata, all_files, structure, file_contents
                
        Returns:
            Dict[str, Any]: Comprehensive analysis dictionary containing:
                - repository_analysis: Project type, technologies, architecture
                - build_ecosystem: Build tools, package managers, bundlers
                - commands: Detailed commands for all development scenarios  
                - environment: Required versions and dependencies
                - notes: Additional insights and recommendations
                - recommended_workflow: Step-by-step development process
                - error: Error message if analysis failed
                
        Note:
            Falls back gracefully if AI analysis fails, returning error information
            for debugging and user feedback.
        """
        # Validate input data
        if 'error' in repo_data:
            logger.error(f"Repository data contains error: {repo_data['error']}")
            return repo_data

        required_keys = ['owner', 'repo', 'metadata', 'file_contents', 'structure']
        missing_keys = [key for key in required_keys if key not in repo_data]
        if missing_keys:
            error_msg = f"Missing required repository data keys: {missing_keys}"
            logger.error(error_msg)
            return {'error': error_msg}

        try:
            # Choose between custom and default prompt
            if self.config.get('custom_prompt_template'):
                logger.info("Using custom prompt template for analysis")
                prompt = self._build_custom_prompt(repo_data)
            else:
                logger.info("Using default comprehensive prompt for analysis")
                prompt = self._build_default_comprehensive_prompt(repo_data)
            
            logger.info(f"Starting AI analysis for {repo_data['owner']}/{repo_data['repo']}")
            
            # Call AI model with comprehensive prompt
            ai_response = self._call_ai_model(prompt)
            
            if isinstance(ai_response, str):
                try:
                    # Extract JSON from AI response
                    start_idx = ai_response.find('{')
                    end_idx = ai_response.rfind('}') + 1
                    
                    if start_idx != -1 and end_idx > 0:
                        json_str = ai_response[start_idx:end_idx]
                        analysis_result = json.loads(json_str)
                        
                        # Add metadata to the analysis
                        analysis_result['analysis_metadata'] = {
                            'analyzer_version': Constants.APP_VERSION,
                            'model_used': self.model,
                            'analysis_timestamp': datetime.now().isoformat(),
                            'repository': f"{repo_data['owner']}/{repo_data['repo']}",
                            'files_analyzed': len(repo_data['file_contents']),
                            'total_files': repo_data.get('total_files', 0)
                        }
                        
                        logger.info("AI analysis completed successfully")
                        return analysis_result
                        
                    else:
                        raise ValueError("No valid JSON found in AI response")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse AI response as JSON: {e}")
                    logger.debug(f"AI response (first 500 chars): {ai_response[:500]}")
                    return {
                        'error': 'AI returned invalid JSON format',
                        'error_details': str(e),
                        'raw_response_preview': ai_response[:200] + '...' if len(ai_response) > 200 else ai_response
                    }
            else:
                logger.error(f"Unexpected AI response type: {type(ai_response)}")
                return {'error': 'Unexpected AI response format', 'response_type': str(type(ai_response))}

        except Exception as e:
            error_msg = f"AI analysis failed: {e}"
            logger.error(error_msg)
            return {
                'error': error_msg,
                'error_type': type(e).__name__,
                'repository': f"{repo_data.get('owner', 'unknown')}/{repo_data.get('repo', 'unknown')}"
            }

    def _build_custom_prompt(self, repo_data: Dict[str, Any]) -> str:
        """
        Build a custom analysis prompt from user-provided template with variable substitution.

        Args:
            repo_data (Dict[str, Any]): Repository context data
            
        Returns:
            str: Formatted custom prompt with all variables substituted
            
        Note:
            Supported template variables:
            - {REPO_NAME}: owner/repo format
            - {DESCRIPTION}: Repository description
            - {LANGUAGE}: Primary programming language
            - {TOPICS}: Comma-separated topic tags
            - {TOTAL_FILES}: Total file count
            - {FILE_STRUCTURE}: Formatted file list
            - {FILE_CONTENTS}: Formatted file contents
            - {STRUCTURE_ANALYSIS}: JSON structure analysis
            - {COMMAND_CATEGORIES}: Available command categories
        """
        template = self.config['custom_prompt_template']
        
        # Prepare all replacement variables
        replacements = {
            '{REPO_NAME}': f"{repo_data['owner']}/{repo_data['repo']}",
            '{DESCRIPTION}': repo_data['metadata'].get('description', 'No description provided'),
            '{LANGUAGE}': repo_data['metadata'].get('language', 'Not specified'),
            '{TOPICS}': ', '.join(repo_data['metadata'].get('topics', [])) or 'None specified',
            '{TOTAL_FILES}': str(repo_data.get('total_files', len(repo_data.get('all_files', [])))),
            '{FILE_STRUCTURE}': '\n'.join(f"- {f}" for f in repo_data.get('all_files', [])[:Constants.MAX_FILES_IN_PROMPT]),
            '{FILE_CONTENTS}': self._format_file_contents(repo_data.get('file_contents', {})),
            '{STRUCTURE_ANALYSIS}': json.dumps(repo_data.get('structure', {}), indent=2),
            '{COMMAND_CATEGORIES}': ', '.join(self.config['command_categories'])
        }
        
        # Apply all replacements to template
        formatted_prompt = template
        for placeholder, value in replacements.items():
            formatted_prompt = formatted_prompt.replace(placeholder, str(value))
        
        logger.debug(f"Built custom prompt with {len(replacements)} variable substitutions")
        return formatted_prompt

    def _build_default_comprehensive_prompt(self, repo_data: Dict[str, Any]) -> str:
        """
        Build the default comprehensive analysis prompt with all repository context.

        Args:
            repo_data (Dict[str, Any]): Repository context data
            
        Returns:
            str: Comprehensive analysis prompt for AI model
            
        Note:
            This prompt is designed to extract maximum value from repository analysis,
            covering build systems, development workflows, deployment, and best practices.
        """
        # Format file contents and structure for prompt
        file_contents_text = self._format_file_contents(repo_data.get('file_contents', {}))
        structure_summary = json.dumps(repo_data.get('structure', {}), indent=2)
        
        # Prepare metadata
        metadata = repo_data.get('metadata', {})
        topics = metadata.get('topics', [])
        topics_str = ', '.join(topics) if topics else 'None specified'
        
        # Build comprehensive prompt
        prompt = f"""
You are a world-class senior software engineer and DevOps architect with expertise across all programming languages, frameworks, build systems, and development workflows. Your task is to analyze this repository comprehensively and provide detailed, accurate, and actionable insights.

REPOSITORY CONTEXT:
Repository: {repo_data['owner']}/{repo_data['repo']}
Description: {metadata.get('description', 'No description provided')}
Primary Language: {metadata.get('language', 'Not detected')}
Topics/Tags: {topics_str}
Stars: {metadata.get('stargazers_count', 0):,}
Forks: {metadata.get('forks_count', 0):,}
Size: {metadata.get('size', 0):,} KB
Created: {metadata.get('created_at', 'Unknown')}
Last Updated: {metadata.get('updated_at', 'Unknown')}
Default Branch: {metadata.get('default_branch', 'main')}
Total Files: {repo_data.get('total_files', 0):,}
Files Analyzed: {len(repo_data.get('file_contents', {})):,}

REPOSITORY STRUCTURE ANALYSIS:
{structure_summary}

ANALYZED FILES AND CONTENTS:
{file_contents_text}

ANALYSIS INSTRUCTIONS:
Provide a comprehensive analysis focusing on practical, executable insights. Be confident in your recommendations and provide specific commands that developers can immediately use. Consider the full development lifecycle from setup to deployment.

KEY ANALYSIS AREAS:
1. TECHNOLOGY STACK: Identify all technologies, frameworks, and tools with versions where possible
2. BUILD SYSTEM: Understand build processes, compilation steps, and optimization strategies  
3. PROJECT ARCHITECTURE: Analyze structure patterns, design decisions, and scalability aspects
4. DEVELOPMENT WORKFLOW: Cover local development, testing strategies, and quality assurance
5. ENVIRONMENT SETUP: Specify requirements, dependencies, and configuration needs
6. DEPLOYMENT: Identify deployment targets, CI/CD patterns, and production considerations
7. MAINTENANCE: Code quality, security, updates, and long-term sustainability

SPECIAL CONSIDERATIONS:
- Handle monorepos by providing workspace-specific commands
- Support multi-language projects with appropriate toolchain commands
- Consider subdirectory structures (use 'cd subdirectory &&' when needed)
- Provide alternatives when multiple approaches are valid
- Include performance and security best practices
- Address both development and production scenarios

OUTPUT FORMAT:
Return ONLY a valid JSON object with this exact structure (no markdown, no additional text):

{{
    "repository_analysis": {{
        "primary_technology": "Main technology/framework",
        "technology_stack": ["comprehensive list of all technologies"],
        "framework_stack": ["all frameworks and libraries"],
        "architecture_type": "monorepo|microservices|monolith|library|application|hybrid",
        "project_complexity": "simple|moderate|complex|enterprise",
        "development_stage": "experimental|early|mature|legacy|maintained",
        "deployment_targets": ["cloud platforms, containers, or deployment types"],
        "scalability_indicators": ["patterns suggesting scale requirements"],
        "security_features": ["security-related implementations found"]
    }},
    "build_ecosystem": {{
        "primary_build_tool": "main build orchestrator",
        "package_managers": ["npm|yarn|pip|maven|gradle|cargo|go|composer|etc"],
        "bundlers": ["webpack|vite|rollup|parcel|esbuild|etc"],
        "compilers": ["typescript|babel|rustc|javac|gcc|etc"],
        "task_runners": ["npm-scripts|gulp|grunt|make|invoke|etc"],
        "preprocessors": ["sass|less|postcss|etc"],
        "code_generators": ["tools that generate code or assets"]
    }},
    "commands": {{
        "environment_setup": "Command to set up development environment",
        "install_dependencies": "Install all required dependencies",  
        "install_dev_dependencies": "Install development-only dependencies",
        "clean_install": "Clean installation (remove cache/lock files first)",
        "update_dependencies": "Update dependencies to latest versions",
        "build_development": "Build for development with debugging",
        "build_production": "Optimized production build",
        "build_library": "Build as distributable library/package",
        "start_development": "Start local development server with hot reload",
        "start_production": "Start production server",
        "watch_mode": "Watch files and rebuild automatically",
        "test_all": "Run complete test suite",
        "test_unit": "Run unit tests only",
        "test_integration": "Run integration tests",
        "test_e2e": "Run end-to-end tests",
        "test_watch": "Run tests in watch mode",
        "test_coverage": "Generate test coverage report",
        "lint_code": "Run code linting",
        "lint_fix": "Auto-fix linting issues where possible",
        "format_code": "Format code according to style rules",
        "type_check": "Run static type checking",
        "security_audit": "Run security vulnerability scan",
        "dependency_check": "Check for outdated or vulnerable dependencies",
        "bundle_analyze": "Analyze bundle size and composition",
        "performance_profile": "Profile application performance",
        "docker_build": "Build Docker container image",
        "docker_run": "Run application in Docker container",
        "docker_compose": "Run with docker-compose (if applicable)",
        "deploy_staging": "Deploy to staging environment",
        "deploy_production": "Deploy to production environment",
        "database_migrate": "Run database migrations",
        "database_seed": "Seed database with initial data",
        "database_reset": "Reset database to clean state",
        "generate_docs": "Generate project documentation",
        "clean_build": "Clean all build artifacts",
        "ci_local": "Run CI pipeline locally",
        "release": "Create and publish a new release",
        "maintenance": "General maintenance tasks"
    }},
    "environment_requirements": {{
        "runtime_versions": {{
            "java": "specific Java version required (e.g., '8', '11', '17', '21') or 'any'",
            "node": "specific Node.js version required (e.g., '16.x', '18.x', '20.x', 'latest')",
            "npm": "specific npm version required (e.g., '8.x', '9.x', '10.x') or 'latest'",
            "python": "specific Python version required (e.g., '3.8', '3.9', '3.10', '3.11', '3.12') or 'latest'",
            "pip": "specific pip version required or 'latest'",
            "go": "specific Go version required (e.g., '1.19', '1.20', '1.21') or 'latest'",
            "rust": "specific Rust version required (e.g., '1.70', 'stable', 'beta') or 'latest'",
            "dotnet": "specific .NET version required (e.g., '6.0', '7.0', '8.0') or 'latest'",
            "php": "specific PHP version required (e.g., '8.1', '8.2', '8.3') or 'latest'",
            "ruby": "specific Ruby version required (e.g., '3.0', '3.1', '3.2') or 'latest'",
            "kotlin": "specific Kotlin version required or 'latest'",
            "scala": "specific Scala version required (e.g., '2.13', '3.x') or 'latest'"
        }},
        "build_files_available": {{
            "has_maven_wrapper": "true if mvnw/mvnw.cmd exists, false otherwise",
            "has_gradle_wrapper": "true if gradlew/gradlew.bat exists, false otherwise",
            "has_npm_scripts": "true if package.json has scripts section",
            "has_yarn_lock": "true if yarn.lock exists",
            "has_pnpm_lock": "true if pnpm-lock.yaml exists",
            "has_poetry": "true if pyproject.toml with poetry exists",
            "has_pipenv": "true if Pipfile exists",
            "has_requirements": "true if requirements.txt exists",
            "has_setup_py": "true if setup.py exists",
            "has_go_mod": "true if go.mod exists",
            "has_cargo_toml": "true if Cargo.toml exists",
            "has_composer_json": "true if composer.json exists",
            "has_gemfile": "true if Gemfile exists",
            "has_dotnet_proj": "true if .csproj/.fsproj/.vbproj files exist",
            "maven_pom_location": "path to pom.xml file",
            "gradle_build_location": "path to build.gradle file",
            "package_json_location": "path to package.json file",
            "go_mod_location": "path to go.mod file",
            "cargo_toml_location": "path to Cargo.toml file",
            "requirements_location": "path to requirements.txt file",
            "dockerfile_location": "path to Dockerfile if present",
            "makefile_location": "path to Makefile if present"
        }},
        "version_specifications": {{
            "detected_from": ["list of files where version requirements were detected"],
            "java_source_target": "Java source/target version from pom.xml or build.gradle",
            "maven_compiler_version": "Maven compiler plugin version requirement",
            "spring_boot_version": "Spring Boot version if detected",
            "node_engines": "Node.js engines requirement from package.json",
            "npm_engines": "npm version requirement from package.json engines",
            "python_requires": "Python version from setup.py or pyproject.toml",
            "poetry_python": "Python version requirement from pyproject.toml [tool.poetry.dependencies]",
            "pipenv_python": "Python version from Pipfile",
            "go_version": "Go version from go.mod file",
            "rust_msrv": "Minimum Supported Rust Version from Cargo.toml",
            "dotnet_target_framework": ".NET target framework from .csproj files",
            "php_require": "PHP version from composer.json require",
            "ruby_version": "Ruby version from Gemfile or .ruby-version",
            "kotlin_version": "Kotlin version from build files",
            "scala_version": "Scala version from build.sbt or build.gradle"
        }},
        "system_dependencies": ["system-level packages required"],
        "environment_variables": ["required environment variables"],
        "optional_tools": ["recommended but not required tools"],
        "ide_recommendations": ["recommended IDEs and extensions"]
    }},
    "development_workflow": {{
        "setup_steps": ["ordered list of initial setup steps"],
        "daily_workflow": ["typical development workflow steps"],
        "testing_strategy": "Description of testing approach and best practices",
        "code_quality": "Code quality tools and processes in use",
        "collaboration": "Team collaboration tools and practices",
        "release_process": "How releases are created and deployed"
    }},
    "insights_and_recommendations": {{
        "architectural_strengths": ["positive aspects of current architecture"],
        "potential_improvements": ["specific suggestions for improvement"],
        "security_considerations": ["security-related observations and recommendations"], 
        "performance_notes": ["performance-related insights"],
        "maintainability": "Assessment of code maintainability and technical debt",
        "scalability_assessment": "How well the project handles scale",
        "technology_modernization": ["suggestions for tech stack updates"],
        "best_practices_compliance": "Adherence to industry best practices"
    }},
    "troubleshooting": {{
        "common_issues": ["typical problems developers might encounter"],
        "debugging_commands": ["commands useful for debugging issues"],
        "log_locations": ["where to find relevant log files"],
        "health_checks": ["commands to verify system health"]
    }},
    "metadata": {{
        "confidence_score": "high|medium|low - confidence in analysis accuracy",
        "analysis_completeness": "complete|partial|limited - how complete the analysis is",
        "recommendations_priority": "high|medium|low - urgency of applying recommendations",
        "maintenance_burden": "low|medium|high - estimated ongoing maintenance needs",
        "learning_curve": "easy|moderate|steep - difficulty for new developers"
    }}
}}

CRITICAL REQUIREMENTS:
1. All commands must be executable and tested-worthy
2. Handle subdirectories with appropriate 'cd' prefixes when needed
3. Provide specific version numbers where detectable
4. Include both development and production scenarios
5. Consider cross-platform compatibility (mention OS-specific commands when necessary)
6. Be thorough but practical - focus on actionable insights
7. Ensure JSON is perfectly valid with no syntax errors
8. Do not include any text outside the JSON structure

SPECIAL FOCUS ON VERSION DETECTION FOR ALL LANGUAGES:

JAVA PROJECTS:
- Examine pom.xml for <maven.compiler.source>, <maven.compiler.target>, <java.version>
- Check build.gradle for sourceCompatibility, targetCompatibility, java toolchain
- Check .java-version files, Dockerfile FROM openjdk:XX
- Detect Spring Boot version from dependencies

NODE.JS PROJECTS:
- Check package.json "engines" field for Node.js and npm versions
- Look for .nvmrc, .node-version files
- Check package-lock.json or yarn.lock for version constraints
- Examine Dockerfile FROM node:XX

PYTHON PROJECTS:
- Check setup.py python_requires, pyproject.toml python requirement
- Look for .python-version, runtime.txt (Heroku), Pipfile python_version
- Examine requirements.txt for specific package versions
- Check Dockerfile FROM python:XX

GO PROJECTS:
- Parse go.mod for go directive (e.g., "go 1.20")
- Check .go-version files
- Look for Dockerfile FROM golang:XX

RUST PROJECTS:
- Check Cargo.toml [package] rust-version for MSRV
- Look for rust-toolchain.toml or rust-toolchain files
- Check .rustc_version files

.NET PROJECTS:
- Examine .csproj, .fsproj files for <TargetFramework>
- Check global.json for SDK version requirements
- Look for Dockerfile FROM mcr.microsoft.com/dotnet

PHP PROJECTS:
- Check composer.json require php version
- Look for .php-version files
- Check Dockerfile FROM php:XX

RUBY PROJECTS:
- Examine Gemfile ruby statement
- Check .ruby-version, .rvmrc files
- Look for Dockerfile FROM ruby:XX

BUILD WRAPPER & TOOL DETECTION:
- Maven: mvnw vs system mvn, wrapper generation capability
- Gradle: gradlew vs system gradle
- Node.js: npm vs yarn vs pnpm (check lock files)
- Python: pip vs poetry vs pipenv (check pyproject.toml, Pipfile)
- .NET: dotnet commands, package restore
- PHP: composer vs system package managers
- Ruby: bundler vs gem
- Go: go mod vs GOPATH mode
- Rust: cargo commands

VERSION CONSTRAINT FILES:
- .tool-versions (asdf), .envrc (direnv)
- Docker files with specific base image versions
- CI files (.github/workflows) with setup-* actions specifying versions

Base your analysis on the actual files and structure provided, not generic assumptions.
"""

        return prompt

    def _call_ai_model(self, prompt: str) -> Union[str, Dict[str, Any]]:
        """
        Call the selected AI model with proper error handling, retries, and rate limiting.

        Args:
            prompt (str): Input prompt for the AI model
            
        Returns:
            Union[str, Dict[str, Any]]: AI response text or error information
            
        Raises:
            AIModelError: If all retry attempts fail
            
        Note:
            Implements exponential backoff for retries and handles various
            API error conditions gracefully.
        """
        
        model_name = Constants.MODEL_NAME_MAP.get(self.model, Constants.MODEL_NAME_MAP[Constants.DEFAULT_MODEL])
        
        for attempt in range(Constants.AI_MAX_RETRIES):
            try:
                logger.debug(f"Calling AI model {model_name} (attempt {attempt + 1}/{Constants.AI_MAX_RETRIES})")
                
                # Prepare request with timeout and proper parameters
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                # Extract response content
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    logger.info(f"AI model {model_name} responded successfully")
                    return content
                else:
                    raise AIModelError("AI model returned empty response")
                
            except Exception as e:
                error_msg = f"AI model call failed (attempt {attempt + 1}): {e}"
                logger.warning(error_msg)
                
                # Don't retry on certain error types
                error_str = str(e).lower()
                if any(term in error_str for term in ['authentication', 'api_key', 'unauthorized', 'forbidden']):
                    logger.error("Authentication error - not retrying")
                    raise AIModelError(f"Authentication failed for {self.model}: {e}")
                
                # If this is the last attempt, raise the exception
                if attempt == Constants.AI_MAX_RETRIES - 1:
                    logger.error(f"All {Constants.AI_MAX_RETRIES} AI model attempts failed")
                    raise AIModelError(f"AI model {model_name} failed after {Constants.AI_MAX_RETRIES} attempts: {e}")
                
                # Wait before retrying with exponential backoff
                wait_time = Constants.AI_RETRY_DELAY * (2 ** attempt)
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
        
        # Should never reach here due to exception handling above
        raise AIModelError("Unexpected error in AI model call")

    def save_analysis_result(self, analysis_result: Dict[str, Any], owner: str, repo: str) -> str:
        """
        Save analysis result to a structured output file with proper error handling.
        
        Args:
            analysis_result (Dict[str, Any]): Complete analysis result
            owner (str): Repository owner
            repo (str): Repository name
            
        Returns:
            str: Path to the saved output file
            
        Note:
            Creates directory structure if needed and handles file write errors gracefully.
        """
        try:
            # Create output directory structure
            output_dir = Path(owner)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp for uniqueness
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{repo}_{timestamp}.json"
            output_path = output_dir / output_filename
            
            # Write analysis result with pretty formatting
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, indent=2, ensure_ascii=False, sort_keys=False)
            
            logger.info(f"Analysis result saved to: {output_path}")
            
            # Also create a "latest" symlink/copy for convenience
            latest_path = output_dir / f"{repo}_latest.json"
            try:
                if latest_path.exists():
                    latest_path.unlink()
                # Create a copy rather than symlink for Windows compatibility
                with open(latest_path, 'w', encoding='utf-8') as f:
                    json.dump(analysis_result, f, indent=2, ensure_ascii=False, sort_keys=False)
                logger.debug(f"Latest analysis link created: {latest_path}")
            except Exception as e:
                logger.warning(f"Could not create latest analysis link: {e}")
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to save analysis result: {e}")
            # Fallback: try to save in current directory
            try:
                fallback_path = Path(f"{owner}_{repo}_analysis.json")
                with open(fallback_path, 'w', encoding='utf-8') as f:
                    json.dump(analysis_result, f, indent=2, ensure_ascii=False)
                logger.info(f"Analysis saved to fallback location: {fallback_path}")
                return str(fallback_path)
            except Exception as fallback_error:
                logger.error(f"Fallback save also failed: {fallback_error}")
                raise RepositoryAnalyzerError(f"Could not save analysis result: {e}")


def validate_environment() -> Dict[str, Any]:
    """
    Validate the runtime environment and check for required dependencies.
    
    Returns:
        Dict[str, Any]: Environment validation results
        
    Note:
        Checks for required Python packages, environment variables,
        and system configuration that might affect analysis quality.
    """
    validation_results = {
        'python_version': sys.version,
        'required_packages': {},
        'environment_variables': {},
        'warnings': [],
        'errors': []
    }
    
    # Check required packages
    required_packages = ['requests', 'openai', 'toml', 'yaml']
    for package in required_packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            validation_results['required_packages'][package] = version
        except ImportError:
            validation_results['errors'].append(f"Required package '{package}' not found")
    
    # Check environment variables
    env_vars_to_check = [
        Constants.GITHUB_TOKEN_ENV,
        Constants.AI_API_KEY_ENV
    ]

    for env_var in env_vars_to_check:
        value = os.getenv(env_var)
        validation_results['environment_variables'][env_var] = 'set' if value else 'not set'

    # Check if AI API key is available
    ai_key_available = bool(os.getenv(Constants.AI_API_KEY_ENV))
    if not ai_key_available:
        validation_results['errors'].append(f"AI API key not found. Please set {Constants.AI_API_KEY_ENV} environment variable")
    
    # GitHub token warning
    if not os.getenv(Constants.GITHUB_TOKEN_ENV):
        validation_results['warnings'].append(
            f"{Constants.GITHUB_TOKEN_ENV} not set - API rate limits will apply"
        )
    
    return validation_results


def print_usage():
    """Print comprehensive usage information and examples."""
    usage_text = f"""
{Constants.APP_NAME} v{Constants.APP_VERSION}
{'-' * (len(Constants.APP_NAME) + len(Constants.APP_VERSION) + 3)}

DESCRIPTION:
    Analyze GitHub repositories using AI to generate comprehensive build commands,
    development workflows, and architectural insights. Supports multiple AI providers
    and handles complex project structures including monorepos.

USAGE:
    python {sys.argv[0]} <github_repo_url> [model] [config_file]

ARGUMENTS:
    github_repo_url    GitHub repository URL (required)
                      Examples: https://github.com/owner/repo
                               https://github.com/owner/repo.git
                               git@github.com:owner/repo.git

    model             AI model to use (optional, default: {Constants.DEFAULT_MODEL})
                      Available models: {', '.join(Constants.MODEL_NAME_MAP.keys())}

    config_file       Configuration file path (optional)
                      Supported formats: .toml, .yaml/.yml, .json

EXAMPLES:
    # Basic analysis with default model
    python {sys.argv[0]} https://github.com/facebook/react

    # Use specific AI model
    python {sys.argv[0]} https://github.com/microsoft/vscode claude-opus

    # Use custom configuration
    python {sys.argv[0]} https://github.com/google/go gpt-4 my_config.toml

ENVIRONMENT VARIABLES:
    Required:
    AI_API_KEY           Universal AI API key for all providers
                        Works with Claude, OpenAI GPT, and Google Gemini models

    Optional:
    GITHUB_TOKEN         GitHub Personal Access Token (recommended)
                        Without this, rate limits apply (60 vs 5000 requests/hour)
    AI_API_BASE_URL      Custom API base URL (default: https://llm.labs.blackduck.com)

OUTPUT:
    Analysis results are saved to: <owner>/<repo>_<timestamp>.json
    A latest copy is also saved as: <owner>/<repo>_latest.json
    Detailed logs are saved to: logs/repo_analyzer_<timestamp>.log

CONFIGURATION:
    Configuration files can customize analysis behavior:
    
    [TOML Example - config.toml]
    analysis_depth = "comprehensive"
    max_files_to_analyze = 75
    max_file_size = 15000
    
    [[command_categories]]
    categories = ["setup", "build", "test", "deploy"]
    
    [api_base_urls]
    base_url = "https://custom-ai-endpoint.com/v1"

SUPPORT:
    Repository: https://github.com/SrinathAkkem/repo-analyzer
    Issues: https://github.com/SrinathAkkem/repo-analyzer/issues
    Documentation: https://docs.example.com/repo-analyzer
"""
    print(usage_text)


def main():
    """
    Main entry point for the Universal Repository Analyzer.
    
    Handles command-line argument parsing, environment validation,
    analysis orchestration, and output management.
    
    Exit Codes:
        0: Success
        1: Invalid arguments or usage
        2: Environment validation failed  
        3: Repository analysis failed
        4: File I/O error
    """
    # Print banner
    print(f"\n{Constants.APP_NAME} v{Constants.APP_VERSION}")
    print(f"{'=' * (len(Constants.APP_NAME) + len(Constants.APP_VERSION) + 3)}")
    print(f"Author: {__author__}")
    print(f"License: {__license__}")
    print()

    # Check arguments
    if len(sys.argv) < 2:
        print("❌ Error: Repository URL is required\n")
        print_usage()
        sys.exit(1)
    
    if sys.argv[1] in ['-h', '--help', 'help']:
        print_usage()
        sys.exit(0)

    # Parse command line arguments
    repo_url = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else Constants.DEFAULT_MODEL
    config_file = sys.argv[3] if len(sys.argv) > 3 else None

    # Validate environment
    print("🔍 Validating environment...")
    env_validation = validate_environment()
    
    if env_validation['errors']:
        print("❌ Environment validation failed:")
        for error in env_validation['errors']:
            print(f"   • {error}")
        sys.exit(2)
    
    if env_validation['warnings']:
        print("⚠️  Environment warnings:")
        for warning in env_validation['warnings']:
            print(f"   • {warning}")
    
    print("✅ Environment validation passed")
    print(f"📝 Log file: {log_file_path}")
    print()

    try:
        # Initialize analyzer
        print(f"🚀 Initializing analyzer with model: {model}")
        if config_file:
            print(f"📋 Using configuration file: {config_file}")
        
        analyzer = UniversalRepoAnalyzer(model=model, config_file=config_file)
        
        # Fetch repository context
        print(f"🔄 Analyzing repository: {repo_url}")
        print("   └── Fetching repository context...")
        
        context = analyzer.get_full_repository_context(repo_url)
        
        if 'error' in context:
            print(f"❌ Failed to fetch repository context: {context['error']}")
            
            # Save error information
            try:
                error_output_path = analyzer.save_analysis_result(context, 
                    context.get('owner', 'unknown'), 
                    context.get('repo', 'unknown'))
                print(f"💾 Error details saved to: {error_output_path}")
            except Exception:
                pass
            
            sys.exit(3)
        
        print(f"✅ Repository context fetched:")
        print(f"   └── {context['total_files']} total files")
        print(f"   └── {context['analyzed_files']} files analyzed in detail")
        
        # Perform AI analysis
        print("🧠 Performing AI analysis...")
        analysis = analyzer.analyze_with_ai(context)
        
        if 'error' in analysis:
            print(f"❌ AI analysis failed: {analysis['error']}")
            
            # Save error information
            try:
                error_output_path = analyzer.save_analysis_result(analysis, context['owner'], context['repo'])
                print(f"💾 Error details saved to: {error_output_path}")
            except Exception:
                pass
                
            sys.exit(3)
        
        # Save results
        print("💾 Saving analysis results...")
        output_path = analyzer.save_analysis_result(analysis, context['owner'], context['repo'])
        
        # Print success summary
        print("\n🎉 Analysis completed successfully!")
        print(f"📊 Results saved to: {output_path}")
        print(f"📈 Repository: {context['owner']}/{context['repo']}")
        print(f"🔧 Model used: {analyzer.model}")
        
        # Print key insights if available
        if 'repository_analysis' in analysis:
            repo_analysis = analysis['repository_analysis']
            print(f"🏗️  Architecture: {repo_analysis.get('architecture_type', 'Unknown')}")
            print(f"💻 Primary tech: {repo_analysis.get('primary_technology', 'Unknown')}")
            if 'technology_stack' in repo_analysis and repo_analysis['technology_stack']:
                tech_count = len(repo_analysis['technology_stack'])
                print(f"🛠️  Technologies: {tech_count} identified")
        
        # Print JSON output for programmatic consumption
        print("\n" + "="*60)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
        logger.info("Analysis interrupted by user (KeyboardInterrupt)")
        sys.exit(1)
        
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        logger.error(f"Configuration error: {e}")
        sys.exit(2)
        
    except (GitHubAPIError, AIModelError) as e:
        print(f"❌ Analysis error: {e}")
        logger.error(f"Analysis error: {e}")
        sys.exit(3)
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(4)


if __name__ == "__main__":
    main()
