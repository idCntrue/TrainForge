import json
from datetime import datetime, timezone

from sqlalchemy import select

from yolo_factory.models.domain import ModelVersion, ModelVersionSpec
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import InferenceRunRecord, ModelVersionRecord


class InvalidModelTransition(ValueError):
    pass


class DuplicateModelRegistration(ValueError):
    pass


class PublishedModelDeletion(ValueError):
    pass


class ReferencedModelDeletion(ValueError):
    pass


class ModelVersionRepository:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def create(self, spec: ModelVersionSpec, *, model_id: str) -> ModelVersion:
        config = {
            "selected_classes": list(spec.selected_classes),
            "class_aliases": spec.class_aliases,
            "pt_path": spec.pt_path,
            "metrics": spec.metrics,
            "artifacts": {},
            "environment": {},
            "quality_report": spec.quality_report,
        }
        with session_scope(self._registry) as session:
            existing = session.execute(
                select(ModelVersionRecord.id).where(ModelVersionRecord.training_run_id == spec.training_run_id)
            ).scalar_one_or_none()
            if existing is not None:
                raise DuplicateModelRegistration(f"training run is already registered as model {existing}")
            session.add(ModelVersionRecord(
                id=model_id,
                name=spec.name,
                version=spec.version,
                task_type=spec.task_type,
                training_run_id=spec.training_run_id,
                dataset_release_id=spec.dataset_release_id,
                config_json=json.dumps(config, sort_keys=True),
                status="candidate",
                gates_json=json.dumps({
                    "training": True,
                    "pt": True,
                    "onnx": False,
                    "consistency": False,
                    "independent_test_available": spec.quality_report is not None,
                    "quality_recommended": (spec.quality_report or {}).get("verdict") == "ready",
                }, sort_keys=True),
            ))
        return self.get_required(model_id)

    def get(self, model_id: str) -> ModelVersion | None:
        with session_scope(self._registry) as session:
            record = session.get(ModelVersionRecord, model_id)
            return _to_domain(record) if record else None

    def get_required(self, model_id: str) -> ModelVersion:
        model = self.get(model_id)
        if model is None:
            raise KeyError(model_id)
        return model

    def list(self, *, status: str | None = None) -> list[ModelVersion]:
        statement = select(ModelVersionRecord).order_by(ModelVersionRecord.created_at.desc())
        if status:
            statement = statement.where(ModelVersionRecord.status == status)
        with session_scope(self._registry) as session:
            return [_to_domain(record) for record in session.scalars(statement)]

    def delete(self, model_id: str) -> ModelVersion:
        with session_scope(self._registry) as session:
            record = session.get(ModelVersionRecord, model_id)
            if record is None:
                raise KeyError(model_id)
            if record.status == "published":
                raise PublishedModelDeletion("published models must be archived before deletion")
            inference_id = session.execute(
                select(InferenceRunRecord.id).where(InferenceRunRecord.model_version_id == model_id).limit(1)
            ).scalar_one_or_none()
            if inference_id is not None:
                raise ReferencedModelDeletion(f"model is referenced by inference run {inference_id}")
            model = _to_domain(record)
            session.delete(record)
            return model

    def update_gates(
        self,
        model_id: str,
        gates: dict[str, bool],
        *,
        artifacts: dict[str, dict] | None = None,
        environment: dict[str, str] | None = None,
        gate_report_path: str | None = None,
    ) -> ModelVersion:
        with session_scope(self._registry) as session:
            record = session.get(ModelVersionRecord, model_id)
            if record is None:
                raise KeyError(model_id)
            if record.status in {"published", "archived"}:
                raise InvalidModelTransition("terminal model gates cannot be changed")
            existing_gates = json.loads(record.gates_json)
            gates = {
                **gates,
                "independent_test_available": existing_gates.get("independent_test_available", False),
                "quality_recommended": existing_gates.get("quality_recommended", False),
            }
            record.gates_json = json.dumps(gates, sort_keys=True)
            config = json.loads(record.config_json)
            if artifacts is not None:
                config["artifacts"] = artifacts
            if environment is not None:
                config["environment"] = environment
            record.config_json = json.dumps(config, sort_keys=True)
            if gate_report_path is not None:
                record.gate_report_path = gate_report_path
            hard_gates = {key: value for key, value in gates.items() if key != "quality_recommended"}
            record.status = "candidate" if all(hard_gates.values()) else "blocked"
        return self.get_required(model_id)

    def publish(self, model_id: str) -> ModelVersion:
        with session_scope(self._registry) as session:
            record = session.get(ModelVersionRecord, model_id)
            if record is None:
                raise KeyError(model_id)
            gates = json.loads(record.gates_json)
            if not gates.get("independent_test_available", False):
                raise InvalidModelTransition("independent test result is required before publication")
            hard_gates = {key: value for key, value in gates.items() if key != "quality_recommended"}
            if record.status not in {"candidate", "blocked"} or not hard_gates or not all(hard_gates.values()):
                raise InvalidModelTransition("all release gates must pass before publication")
            record.status = "published"
            record.published_at = datetime.now(timezone.utc)
        return self.get_required(model_id)

    def archive(self, model_id: str) -> ModelVersion:
        with session_scope(self._registry) as session:
            record = session.get(ModelVersionRecord, model_id)
            if record is None:
                raise KeyError(model_id)
            if record.status != "published":
                raise InvalidModelTransition("only published models can be archived")
            record.status = "archived"
            record.archived_at = datetime.now(timezone.utc)
        return self.get_required(model_id)


def _to_domain(record: ModelVersionRecord) -> ModelVersion:
    config = json.loads(record.config_json)
    return ModelVersion(
        id=record.id,
        spec=ModelVersionSpec(
            name=record.name,
            version=record.version,
            task_type=record.task_type,
            training_run_id=record.training_run_id,
            dataset_release_id=record.dataset_release_id,
            selected_classes=tuple(config["selected_classes"]),
            class_aliases=config["class_aliases"],
            pt_path=config["pt_path"],
            metrics=config["metrics"],
            quality_report=config.get("quality_report"),
        ),
        status=record.status,
        gates=json.loads(record.gates_json),
        artifacts=config.get("artifacts", {}),
        environment=config.get("environment", {}),
        gate_report_path=record.gate_report_path,
        created_at=record.created_at,
        updated_at=record.updated_at,
        published_at=record.published_at,
        archived_at=record.archived_at,
    )
