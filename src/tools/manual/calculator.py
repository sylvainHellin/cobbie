# python packages
import math
import re

def calculator(expression: str) -> str:
    """Performs basic mathematical calculations from a text expression.
    
    This function can handle:
    - Basic arithmetic operations (+, -, *, /, ^)
    - Parentheses for operation precedence
    - Common mathematical functions (sqrt, sin, cos, etc.)
    - Unit conversions and ratios
    - Percentage calculations
    
    Args:
        expression (str): A string containing the mathematical expression to evaluate.
            Examples:
            - "2 + 2"
            - "5 * (3 + 2)"
            - "sqrt(16)"
            - "50% of 200"
            - "sin(45)"
            - "3/4 as percentage"
    
    Returns:
        str: Result of the calculation as a string, rounded to 2 decimal places.
            Returns "Error" if the calculation cannot be performed.
    """
    try:
        # Clean and normalize the expression
        expression = _clean_expression(expression.lower())
        
        # Handle percentage calculations
        if "%" in expression or " as percentage" in expression:
            return _handle_percentage(expression)
            
        # Handle unit conversions (if needed)
        if " to " in expression or " in " in expression:
            return _handle_unit_conversion(expression)
        
        # Handle mathematical functions
        if any(func in expression for func in ["sqrt", "sin", "cos", "tan", "log"]):
            return _handle_math_function(expression)
            
        # Evaluate basic arithmetic
        result = eval(_prepare_expression(expression))
        return str(round(float(result), 2))
        
    except Exception as e:
        return f"Error: {str(e)}"

def _clean_expression(expr: str) -> str:
    """Cleans and normalizes the input expression."""
    # Remove extra spaces
    expr = re.sub(r'\s+', ' ', expr.strip())
    # Replace 'x' or '×' with '*'
    expr = expr.replace('x', '*').replace('×', '*')
    # Replace '^' with '**' for exponentiation
    expr = expr.replace('^', '**')
    return expr

def _prepare_expression(expr: str) -> str:
    """Prepares expression for safe evaluation."""
    # Only allow safe characters and operations
    if not re.match(r'^[0-9\s\+\-\*\/\(\)\.\,\%]*$', expr):
        raise ValueError("Invalid characters in expression")
    return expr

def _handle_percentage(expr: str) -> str:
    """Handles percentage calculations."""
    if " of " in expr:
        # Calculate percentage of a number (e.g., "50% of 200")
        percentage, number = expr.split(" of ")
        percentage = float(percentage.strip("%")) / 100
        number = float(number)
        return str(round(percentage * number, 2))
    elif " as percentage" in expr:
        # Convert decimal to percentage (e.g., "0.5 as percentage")
        number = float(expr.replace(" as percentage", ""))
        return str(round(number * 100, 2)) + "%"
    else:
        raise ValueError("Invalid percentage calculation")

def _handle_math_function(expr: str) -> str:
    """Handles mathematical functions."""
    # Extract function name and argument
    match = re.match(r'(sqrt|sin|cos|tan|log)\((.*?)\)', expr)
    if not match:
        raise ValueError("Invalid function format")
        
    func_name, arg = match.groups()
    arg = float(arg)
    
    if func_name == 'sqrt':
        result = math.sqrt(arg)
    elif func_name == 'sin':
        result = math.sin(math.radians(arg))
    elif func_name == 'cos':
        result = math.cos(math.radians(arg))
    elif func_name == 'tan':
        result = math.tan(math.radians(arg))
    elif func_name == 'log':
        result = math.log10(arg)
    
    return str(round(result, 2))

def _handle_unit_conversion(expr: str) -> str:
    """Placeholder for unit conversion handling."""
    # This could be expanded to handle various unit conversions
    raise NotImplementedError("Unit conversion not implemented yet")

if __name__ == "__main__":
    # Test cases
    test_expressions = [
        "2 + 2",
        "5 * (3 + 2)",
        "sqrt(16)",
        "50% of 200",
        "0.75 as percentage",
        "sin(45)",
        "10 / 3"
    ]
    
    for expr in test_expressions:
        print(f"{expr} = {calculator(expr)}")
# %% 