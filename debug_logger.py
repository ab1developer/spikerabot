import logging
import traceback
import os
from datetime import datetime
from config_loader import load_config

class DebugLogger:
    def __init__(self):
        try:
            config = load_config()
            log_dir = config.log_directory
            debug_filename = config.debug_log_file
            
            # Create logs directory if it doesn't exist
            os.makedirs(log_dir, exist_ok=True)
            
            # Combine directory and filename
            self.log_file = os.path.join(log_dir, debug_filename)
        except:
            self.log_file = "debug.log"
        
        # Ensure log file exists
        try:
            with open(self.log_file, 'a') as f:
                f.write(f"\n=== Debug session started at {datetime.now()} ===\n")
        except Exception as e:
            print(f"Failed to create debug log file: {e}")
        
        # Setup logging
        self.logger = logging.getLogger('spikerabot_debug')
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file, mode='a')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
    
    def log_error(self, error_msg: str, exception: Exception = None):
        """Log error with full traceback"""
        try:
            self.logger.error(f"ERROR: {error_msg}")
            if exception:
                self.logger.error(f"Exception: {str(exception)}")
                self.logger.error(f"Traceback: {traceback.format_exc()}")
        except:
            # Fallback to file write if logger fails
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"{datetime.now()} - ERROR: {error_msg}\n")
                    if exception:
                        f.write(f"{datetime.now()} - Exception: {str(exception)}\n")
                        f.write(f"{datetime.now()} - Traceback: {traceback.format_exc()}\n")
            except:
                print(f"Failed to log error: {error_msg}")
    
    def log_info(self, info_msg: str):
        """Log info message"""
        try:
            self.logger.info(info_msg)
        except:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"{datetime.now()} - INFO: {info_msg}\n")
            except:
                print(f"Failed to log info: {info_msg}")
    
    def log_debug(self, debug_msg: str):
        """Log debug message"""
        try:
            self.logger.debug(debug_msg)
        except:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"{datetime.now()} - DEBUG: {debug_msg}\n")
            except:
                print(f"Failed to log debug: {debug_msg}")

# Global debug logger instance
debug_logger = DebugLogger()