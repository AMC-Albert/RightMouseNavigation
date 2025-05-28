import bpy
import time


class FocalLengthManager:
    """Manages focal length transitions for walk/fly mode"""
    
    def __init__(self):
        self.original_lens = None
        self.is_transitioning = False
        self.transition_start_time = 0.0
        self.transition_duration = 0.12  # Default fallback, will be overridden
        self.transition_initial_lens = None
        self.transition_target_lens = None
        self.is_exit_transition = False
        self.exit_transition_attempted = False
    
    def reset(self):
        """Reset all state variables"""
        self.original_lens = None
        self.is_transitioning = False
        self.transition_start_time = 0.0
        self.transition_initial_lens = None
        self.transition_target_lens = None
        self.is_exit_transition = False
        self.exit_transition_attempted = False
    
    def should_change_focal_length(self, addon_prefs):
        """Check if focal length should be changed based on preferences"""
        walk_focal_length_enable = getattr(addon_prefs, "walk_mode_focal_length_enable", False)
        walk_focal_length = addon_prefs.walk_mode_focal_length
        return walk_focal_length_enable and walk_focal_length > 0
    
    def start_entry_transition(self, context, addon_prefs):
        """Start transition to walk mode focal length"""
        if not self.should_change_focal_length(addon_prefs):
            return
        
        walk_focal_length = addon_prefs.walk_mode_focal_length
        current_lens = context.space_data.lens
        
        self.original_lens = current_lens
        
        if abs(current_lens - walk_focal_length) > 0.001:
            # Check if transitions are disabled (duration = 0)
            if addon_prefs.walk_mode_transition_duration == 0:
                # Instant transition
                context.space_data.lens = walk_focal_length
                return
            
            self.transition_initial_lens = current_lens
            self.transition_target_lens = walk_focal_length
            self.is_transitioning = True
            self.is_exit_transition = False
            self.transition_start_time = time.time()
            # Use duration from preferences
            self.transition_duration = addon_prefs.walk_mode_transition_duration

    def start_exit_transition(self, context, addon_prefs):
        """Start transition back to original focal length"""
        # Prevent repeated attempts
        if self.exit_transition_attempted:
            return False
            
        self.exit_transition_attempted = True
        
        if not self.should_change_focal_length(addon_prefs) or self.original_lens is None:
            return False
        
        current_lens = context.space_data.lens
        
        if abs(current_lens - self.original_lens) > 0.001:
            # Check if transitions are disabled (duration = 0)
            if addon_prefs.walk_mode_transition_duration == 0:
                # Instant transition
                context.space_data.lens = self.original_lens
                self.original_lens = None
                return False  # No need to continue with modal updates
            
            self.transition_initial_lens = current_lens
            self.transition_target_lens = self.original_lens
            self.is_transitioning = True
            self.is_exit_transition = True
            self.transition_start_time = time.time()
            # Use duration from preferences
            self.transition_duration = addon_prefs.walk_mode_transition_duration
            return True
        else:
            # If lens is already at original, just clear the original_lens
            self.original_lens = None
        
        return False
    
    def update_transition(self, context):
        """Update ongoing transition, returns True if transition completed"""
        if not self.is_transitioning:
            return False
        
        elapsed = time.time() - self.transition_start_time
        
        if (self.transition_initial_lens is None or 
            self.transition_target_lens is None):
            self.is_transitioning = False
            return True
        
        if elapsed >= self.transition_duration:
            # Transition complete
            context.space_data.lens = self.transition_target_lens
            
            # Force viewport update
            context.area.tag_redraw()
            
            # Store the exit transition state before clearing
            was_exit_transition = self.is_exit_transition
            
            self.is_transitioning = False
            self.is_exit_transition = False
            
            if was_exit_transition:
                # Clear original lens after successful exit transition
                self.original_lens = None
            
            return True
        else:
            # Interpolate with easing for smoother transitions
            t = elapsed / self.transition_duration
            # Apply ease-out curve for smoother motion
            t = 1 - (1 - t) * (1 - t)
            new_lens = (self.transition_initial_lens + 
                       (self.transition_target_lens - self.transition_initial_lens) * t)
            context.space_data.lens = new_lens
            
            # Force viewport update for smooth visual feedback
            context.area.tag_redraw()
            
            return False
    
    def force_restore_original(self, context, addon_prefs):
        """Force restore to original focal length without transition"""
        if (self.original_lens is not None and 
            self.should_change_focal_length(addon_prefs) and
            context.space_data.type == "VIEW_3D"):
            context.space_data.lens = self.original_lens
            self.original_lens = None
    
    def cleanup(self, context, addon_prefs):
        """Clean up focal length state, restoring original if needed"""
        self.is_transitioning = False
        
        # Final restoration check
        if (self.original_lens is not None and 
            context.space_data.type == "VIEW_3D" and
            self.should_change_focal_length(addon_prefs)):
            context.space_data.lens = self.original_lens
        
        self.original_lens = None
        self.exit_transition_attempted = False
