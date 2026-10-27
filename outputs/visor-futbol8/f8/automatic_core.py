"""Compatibilidad temporal (Fase 0). Importa desde f8.<módulo>; se borrará al cerrar la Fase 1."""
from f8.core.io import write_json,ort_session,crop,iou  # noqa: F401
from f8.deteccion.modelos import Detector,appearance,kit,Encoder,MemoryTracker  # noqa: F401
from f8.campo.proyeccion import project,Registrar,camera_step  # noqa: F401
from f8.identidad.dorsales import number_region,jersey_vote  # noqa: F401
from f8.balon.seleccion import select_ball  # noqa: F401
from f8.acciones.contactos import foot_contacts,infer_possession,action_candidates  # noqa: F401
from f8.publicacion.alineacion_basica import infer_changes  # noqa: F401
