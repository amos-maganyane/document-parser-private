class ConfigError(Exception):
    """Configuration-related errors"""

class ParserError(Exception):
    """Document parsing errors"""

class NormalizationError(Exception):
    """Data normalization errors"""

class ValidationError(Exception):
    """Data validation errors"""