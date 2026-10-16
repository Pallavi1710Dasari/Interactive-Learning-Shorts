# Avatar models

The 3D presenters (`MOTION_AVATARS=vrm`) wear two local VRM 1.0 files:

| File | Who wears it |
|---|---|
| `mentor.vrm` | the explainer (right of the board) |
| `student.vrm` | the asker (lower left) |

The `.vrm` files are not in git (`.gitignore`). The server reads them from
disk on every request (`/api/motion/avatars/<name>`), so replacing a file
needs no code change.

**Placeholders today:** both files are pixiv's `VRM1_Constraint_Twist_Sample.vrm`
from the three-vrm repository
(`packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm`).
Its licence metadata: commercial use by corporations allowed, redistribution
and modification allowed, no credit needed (https://vrm.dev/licenses/1.0/).
While the student file is the very same file as the mentor's, the player
recolours it (`web/src/motion/vrm/looks.ts`) and draws it a little smaller.
Your own two files are drawn as they are.

`shorts/motion_vrm_test.py` checks that each file is VRM 1.0 and allows
commercial use.
