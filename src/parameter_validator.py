class ValidationError(Exception):
    """Custom exception for parameter range violations."""
    pass

class ParameterValidator:
    def __init__(self, schema):
        self.schema = schema

    def validate(self, config):
        """
        Validates the configuration against the provided schema.
        schema format: { key: (type, min, max, unit, required) }
        """
        geom = config.get("geometry", {})
        
        for key, constraints in self.schema.items():
            expected_type, min_val, max_val, unit, required = constraints
            
            # 1. Check if required key is missing
            if required and key not in geom:
                raise ValidationError(f"Missing required parameter: '{key}'")
            
            if key in geom:
                value = geom[key]
                
                # 2. Check type
                if not isinstance(value, expected_type):
                    raise ValidationError(f"Parameter '{key}' must be of type {expected_type.__name__}. Found {type(value).__name__}.")
                
                # 3. Check ranges
                if value < min_val or value > max_val:
                    raise ValidationError(
                        f"Parameter '{key}' ({value}{unit}) is out of valid range: "
                        f"[{min_val}{unit} - {max_val}{unit}] (Source: RAB-ING/RE-ING)."
                    )
        
        return True
