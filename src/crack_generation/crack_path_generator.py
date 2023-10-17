import numpy as np
from scipy.stats import norm

from crack_generation.models import CrackParameters, CrackPath
from crack_generation.util import get_rotation_matrix, increment_by_chance, choose_initial_position, within_bounds, \
    in_object, check_and_mark_overlap
from dataset_generation.models import SurfaceMap

MIN_WIDTH = 1.
MAX_WIDTH_GROW_FACTOR = 0.05
DEFAULT_WIDTH_GROW = 0.2
MAX_TURN_STEPS = 10


def determine_new_points(
        center: np.array,
        width: float,
        angle: float,
        sigma_square: float
) -> tuple[np.array, np.array, np.array]:
    """
    Calculate the new center and top/bot points
    """
    # Calculate new center point
    rotation_matrix = get_rotation_matrix(angle)
    new_center = center + np.dot(rotation_matrix, np.array([1., norm.rvs(scale=sigma_square)]))

    # Calculate the distance from the center for the lines and update them
    offset = np.dot(rotation_matrix, np.array([0., width])) / 2.
    top_point = np.rint(new_center + offset).astype(int)
    bot_point = np.rint(new_center - offset).astype(int)

    return new_center, top_point, bot_point


def generate_path(
        surface: SurfaceMap,
        initial_position: np.array,
        angle: float,
        width: float,
        width_growth_schedule: np.array,
        parameters: CrackParameters
) -> tuple[np.array, np.array]:
    """
    Generate a path and the corresponding top and bottom line from a set of crack parameters
    """
    top_line, bot_line = np.empty((parameters.length, 2), dtype=int), np.empty((parameters.length, 2), dtype=int)
    center = np.copy(initial_position).astype(float)
    sigma_square = parameters.variance ** 2
    overlap_map = np.zeros(surface.mask.shape, dtype=bool)
    moving_through_object = in_object(initial_position, surface)
    idx = 0

    while idx < parameters.length and (width >= MIN_WIDTH or width_growth_schedule[idx] > 0):
        width_grow = width_growth_schedule[idx]  # Set before incrementing idx
        new_center, top_point, bot_point = determine_new_points(center, width, angle, sigma_square)

        # Stop condition: We should be within bounds
        if not within_bounds(top_point, surface) or not within_bounds(bot_point, surface):
            break

        # Check if we're outside the mortar. If we're not, add it to the line
        center_in_object = in_object(np.rint(new_center).astype(int), surface)
        top_in_object = in_object(top_point, surface)
        bot_in_object = in_object(bot_point, surface)

        # NB: This would be nicer as a match statement but Python doesn't want to play along
        if not moving_through_object and (center_in_object or top_in_object or bot_in_object):
            if np.random.random_sample() < parameters.breakthrough_chance:
                moving_through_object = True
                continue

            # Orthogonal to a wall, we need to roll back a bit before making a turn
            # if center_in_object:
            #     idx = int(max(idx - np.ceil(width / 2) - 1, 0))
            #     top_point, bot_point = top_line[max(idx - 1, 0), :], bot_line[max(idx - 1, 0), :]
            #     center = (top_point + bot_point) / 2

            center_int = np.rint(center).astype(int)
            angle = angle + 0.3 * surface.gradient_angles[center_int[1], center_int[0]]
            width = width + 0.3 * (surface.distance_transform[center_int[1], center_int[0]] - width)
        else:
            # Check if the points overlap and only register them if they don't overlap too much
            if check_and_mark_overlap(top_point, bot_point, overlap_map, parameters.allowed_path_overlap):
                center = new_center
                top_line[idx, :] = top_point
                bot_line[idx, :] = bot_point
                idx += 1
                moving_through_object = center_in_object or top_in_object or bot_in_object

            # Update angle and width based on chance
            increments = norm.rvs(size=2, scale=sigma_square)
            angle = increment_by_chance(angle, increments[0], parameters.angle_update_chance)
            width = increment_by_chance(width, increments[1], parameters.width_update_chance) + width_grow

        # Keep angle within [-π, π]
        angle = angle % (np.sign(angle) * -1 * np.pi) if not -np.pi <= angle <= np.pi else angle

    return top_line[:idx], bot_line[:idx]


class CrackPathGenerator:
    """
    Generator class for creating 2D cracks based on CrackParameters.
    """

    def __call__(self, parameters: CrackParameters, surface: SurfaceMap) -> CrackPath:
        """
        Create a top and bottom line of the crack based on the surface.
        """
        total_steps = parameters.length
        start_steps = parameters.start_pointiness
        end_steps = parameters.end_pointiness

        # Account for start and end steps going out of bounds
        if start_steps + end_steps > total_steps:
            boundary_steps = start_steps + end_steps
            start_steps = round(total_steps * start_steps / boundary_steps)
            end_steps = round(total_steps * end_steps / boundary_steps)

        # Initial positions
        current_position, width, angle = choose_initial_position(surface, parameters)

        # Initialise remaining variables
        width_grow_schedule = np.zeros((total_steps,))
        width_grow_increments = max(DEFAULT_WIDTH_GROW, MAX_WIDTH_GROW_FACTOR * width)
        width = max(MIN_WIDTH, width - start_steps * width_grow_increments)
        width_grow_schedule[:start_steps] = width_grow_increments
        width_grow_schedule[total_steps - end_steps:] = -width_grow_increments

        # Launch path generation
        top_line, bot_line = generate_path(
            surface,
            current_position,
            angle,
            width,
            width_grow_schedule,
            parameters
        )

        return CrackPath(top_line, bot_line)
