from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, Enum, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, PrimaryKeyConstraint, String, Text, text
from sqlmodel import Field, Relationship, SQLModel

class Experiments(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('experiment_id', name='experiment_pk'),
    )

    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, primary_key=True))
    name: str = Field(sa_column=Column('name', String(256), nullable=False, unique=True))
    artifact_location: Optional[str] = Field(default=None, sa_column=Column('artifact_location', String(256)))
    lifecycle_stage: Optional[str] = Field(default=None, sa_column=Column('lifecycle_stage', Enum('active', 'deleted')))
    creation_time: Optional[int] = Field(default=None, sa_column=Column('creation_time', BigInteger))
    last_update_time: Optional[int] = Field(default=None, sa_column=Column('last_update_time', BigInteger))

    datasets: list['Datasets'] = Relationship(back_populates='experiment')
    experiment_tags: list['ExperimentTags'] = Relationship(back_populates='experiment')
    logged_models: list['LoggedModels'] = Relationship(back_populates='experiment')
    runs: list['Runs'] = Relationship(back_populates='experiment')
    trace_info: list['TraceInfo'] = Relationship(back_populates='experiment')
    logged_model_metrics: list['LoggedModelMetrics'] = Relationship(back_populates='experiment')
    logged_model_params: list['LoggedModelParams'] = Relationship(back_populates='experiment')
    logged_model_tags: list['LoggedModelTags'] = Relationship(back_populates='experiment')


class InputTags(SQLModel, table=True):
    __tablename__ = 'input_tags'
    __table_args__ = (
        PrimaryKeyConstraint('input_uuid', 'name', name='input_tags_pk'),
    )

    input_uuid: str = Field(sa_column=Column('input_uuid', String(36), primary_key=True))
    name: str = Field(sa_column=Column('name', String(255), primary_key=True))
    value: str = Field(sa_column=Column('value', String(500), nullable=False))


class Inputs(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('source_type', 'source_id', 'destination_type', 'destination_id', name='inputs_pk'),
        Index('index_inputs_destination_type_destination_id_source_type', 'destination_type', 'destination_id', 'source_type'),
        Index('index_inputs_input_uuid', 'input_uuid')
    )

    input_uuid: str = Field(sa_column=Column('input_uuid', String(36), nullable=False))
    source_type: str = Field(sa_column=Column('source_type', String(36), primary_key=True))
    source_id: str = Field(sa_column=Column('source_id', String(36), primary_key=True))
    destination_type: str = Field(sa_column=Column('destination_type', String(36), primary_key=True))
    destination_id: str = Field(sa_column=Column('destination_id', String(36), primary_key=True))
    step: int = Field(sa_column=Column('step', BigInteger, nullable=False, server_default=text("'0'")))


class RegisteredModels(SQLModel, table=True):
    __tablename__ = 'registered_models'
    __table_args__ = (
        PrimaryKeyConstraint('name', name='registered_model_pk'),
    )

    name: str = Field(sa_column=Column('name', String(256), primary_key=True, unique=True))
    creation_time: Optional[int] = Field(default=None, sa_column=Column('creation_time', BigInteger))
    last_updated_time: Optional[int] = Field(default=None, sa_column=Column('last_updated_time', BigInteger))
    description: Optional[str] = Field(default=None, sa_column=Column('description', String(5000)))

    model_versions: list['ModelVersions'] = Relationship(back_populates='registered_models')
    registered_model_aliases: list['RegisteredModelAliases'] = Relationship(back_populates='registered_models')
    registered_model_tags: list['RegisteredModelTags'] = Relationship(back_populates='registered_models')


class Datasets(SQLModel, table=True):
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], ondelete='CASCADE', name='fk_datasets_experiment_id_experiments'),
        PrimaryKeyConstraint('experiment_id', 'name', 'digest', name='dataset_pk'),
        Index('index_datasets_dataset_uuid', 'dataset_uuid'),
        Index('index_datasets_experiment_id_dataset_source_type', 'experiment_id', 'dataset_source_type')
    )

    dataset_uuid: str = Field(sa_column=Column('dataset_uuid', String(36), nullable=False))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, primary_key=True))
    name: str = Field(sa_column=Column('name', String(500), primary_key=True))
    digest: str = Field(sa_column=Column('digest', String(36), primary_key=True))
    dataset_source_type: str = Field(sa_column=Column('dataset_source_type', String(36), nullable=False))
    dataset_source: str = Field(sa_column=Column('dataset_source', Text, nullable=False))
    dataset_schema: Optional[str] = Field(default=None, sa_column=Column('dataset_schema', Text))
    dataset_profile: Optional[str] = Field(default=None, sa_column=Column('dataset_profile', Text))

    experiment: Optional['Experiments'] = Relationship(back_populates='datasets')


class ExperimentTags(SQLModel, table=True):
    __tablename__ = 'experiment_tags'
    __table_args__ = (
        PrimaryKeyConstraint('key', 'experiment_id', name='experiment_tag_pk'),
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', ForeignKey('experiments.experiment_id'), primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(5000)))

    experiment: Optional['Experiments'] = Relationship(back_populates='experiment_tags')


class LoggedModels(SQLModel, table=True):
    __tablename__ = 'logged_models'
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], ondelete='CASCADE', name='fk_logged_models_experiment_id'),
        PrimaryKeyConstraint('model_id', name='logged_models_pk')
    )

    model_id: str = Field(sa_column=Column('model_id', String(36), primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, nullable=False))
    name: str = Field(sa_column=Column('name', String(500), nullable=False))
    artifact_location: str = Field(sa_column=Column('artifact_location', String(1000), nullable=False))
    creation_timestamp_ms: int = Field(sa_column=Column('creation_timestamp_ms', BigInteger, nullable=False))
    last_updated_timestamp_ms: int = Field(sa_column=Column('last_updated_timestamp_ms', BigInteger, nullable=False))
    status: int = Field(sa_column=Column('status', Integer, nullable=False))
    lifecycle_stage: Optional[str] = Field(default=None, sa_column=Column('lifecycle_stage', Enum('active', 'deleted')))
    model_type: Optional[str] = Field(default=None, sa_column=Column('model_type', String(500)))
    source_run_id: Optional[str] = Field(default=None, sa_column=Column('source_run_id', String(32)))
    status_message: Optional[str] = Field(default=None, sa_column=Column('status_message', String(1000)))

    experiment: Optional['Experiments'] = Relationship(back_populates='logged_models')
    logged_model_metrics: list['LoggedModelMetrics'] = Relationship(back_populates='model')
    logged_model_params: list['LoggedModelParams'] = Relationship(back_populates='model')
    logged_model_tags: list['LoggedModelTags'] = Relationship(back_populates='model')


class ModelVersions(SQLModel, table=True):
    __tablename__ = 'model_versions'
    __table_args__ = (
        PrimaryKeyConstraint('name', 'version', name='model_version_pk'),
    )

    name: str = Field(sa_column=Column('name', ForeignKey('registered_models.name', onupdate='CASCADE'), primary_key=True))
    version: int = Field(sa_column=Column('version', Integer, primary_key=True))
    creation_time: Optional[int] = Field(default=None, sa_column=Column('creation_time', BigInteger))
    last_updated_time: Optional[int] = Field(default=None, sa_column=Column('last_updated_time', BigInteger))
    description: Optional[str] = Field(default=None, sa_column=Column('description', String(5000)))
    user_id: Optional[str] = Field(default=None, sa_column=Column('user_id', String(256)))
    current_stage: Optional[str] = Field(default=None, sa_column=Column('current_stage', String(20)))
    source: Optional[str] = Field(default=None, sa_column=Column('source', String(500)))
    run_id: Optional[str] = Field(default=None, sa_column=Column('run_id', String(32)))
    status: Optional[str] = Field(default=None, sa_column=Column('status', String(20)))
    status_message: Optional[str] = Field(default=None, sa_column=Column('status_message', String(500)))
    run_link: Optional[str] = Field(default=None, sa_column=Column('run_link', String(500)))
    storage_location: Optional[str] = Field(default=None, sa_column=Column('storage_location', String(500)))

    registered_models: Optional['RegisteredModels'] = Relationship(back_populates='model_versions')
    model_version_tags: list['ModelVersionTags'] = Relationship(back_populates='model_versions')


class RegisteredModelAliases(SQLModel, table=True):
    __tablename__ = 'registered_model_aliases'
    __table_args__ = (
        ForeignKeyConstraint(['name'], ['registered_models.name'], ondelete='CASCADE', onupdate='CASCADE', name='registered_model_alias_name_fkey'),
        PrimaryKeyConstraint('name', 'alias', name='registered_model_alias_pk')
    )

    alias: str = Field(sa_column=Column('alias', String(256), primary_key=True))
    version: int = Field(sa_column=Column('version', Integer, nullable=False))
    name: str = Field(sa_column=Column('name', String(256), primary_key=True))

    registered_models: Optional['RegisteredModels'] = Relationship(back_populates='registered_model_aliases')


class RegisteredModelTags(SQLModel, table=True):
    __tablename__ = 'registered_model_tags'
    __table_args__ = (
        PrimaryKeyConstraint('key', 'name', name='registered_model_tag_pk'),
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    name: str = Field(sa_column=Column('name', ForeignKey('registered_models.name', onupdate='CASCADE'), primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(5000)))

    registered_models: Optional['RegisteredModels'] = Relationship(back_populates='registered_model_tags')


class Runs(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('run_uuid', name='run_pk'),
    )

    run_uuid: str = Field(sa_column=Column('run_uuid', String(32), primary_key=True))
    name: Optional[str] = Field(default=None, sa_column=Column('name', String(250)))
    source_type: Optional[str] = Field(default=None, sa_column=Column('source_type', Enum('NOTEBOOK', 'JOB', 'LOCAL', 'UNKNOWN', 'PROJECT')))
    source_name: Optional[str] = Field(default=None, sa_column=Column('source_name', String(500)))
    entry_point_name: Optional[str] = Field(default=None, sa_column=Column('entry_point_name', String(50)))
    user_id: Optional[str] = Field(default=None, sa_column=Column('user_id', String(256)))
    status: Optional[str] = Field(default=None, sa_column=Column('status', Enum('SCHEDULED', 'FAILED', 'FINISHED', 'RUNNING', 'KILLED')))
    start_time: Optional[int] = Field(default=None, sa_column=Column('start_time', BigInteger))
    end_time: Optional[int] = Field(default=None, sa_column=Column('end_time', BigInteger))
    source_version: Optional[str] = Field(default=None, sa_column=Column('source_version', String(50)))
    lifecycle_stage: Optional[str] = Field(default=None, sa_column=Column('lifecycle_stage', Enum('active', 'deleted')))
    artifact_uri: Optional[str] = Field(default=None, sa_column=Column('artifact_uri', String(200)))
    experiment_id: Optional[int] = Field(default=None, sa_column=Column('experiment_id', ForeignKey('experiments.experiment_id')))
    deleted_time: Optional[int] = Field(default=None, sa_column=Column('deleted_time', BigInteger))

    experiment: Optional['Experiments'] = Relationship(back_populates='runs')
    latest_metrics: list['LatestMetrics'] = Relationship(back_populates='runs')
    logged_model_metrics: list['LoggedModelMetrics'] = Relationship(back_populates='run')
    metrics: list['Metrics'] = Relationship(back_populates='runs')
    params: list['Params'] = Relationship(back_populates='runs')
    tags: list['Tags'] = Relationship(back_populates='runs')


class TraceInfo(SQLModel, table=True):
    __tablename__ = 'trace_info'
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], name='fk_trace_info_experiment_id'),
        PrimaryKeyConstraint('request_id', name='trace_info_pk'),
        Index('index_trace_info_experiment_id_timestamp_ms', 'experiment_id', 'timestamp_ms')
    )

    request_id: str = Field(sa_column=Column('request_id', String(50), primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, nullable=False))
    timestamp_ms: int = Field(sa_column=Column('timestamp_ms', BigInteger, nullable=False))
    status: str = Field(sa_column=Column('status', String(50), nullable=False))
    execution_time_ms: Optional[int] = Field(default=None, sa_column=Column('execution_time_ms', BigInteger))

    experiment: Optional['Experiments'] = Relationship(back_populates='trace_info')
    trace_request_metadata: list['TraceRequestMetadata'] = Relationship(back_populates='request')
    trace_tags: list['TraceTags'] = Relationship(back_populates='request')


class LatestMetrics(SQLModel, table=True):
    __tablename__ = 'latest_metrics'
    __table_args__ = (
        PrimaryKeyConstraint('key', 'run_uuid', name='latest_metric_pk'),
        Index('index_latest_metrics_run_uuid', 'run_uuid')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    value: float = Field(sa_column=Column('value', Float, nullable=False))
    step: int = Field(sa_column=Column('step', BigInteger, nullable=False))
    is_nan: bool = Field(sa_column=Column('is_nan', Boolean, nullable=False))
    run_uuid: str = Field(sa_column=Column('run_uuid', ForeignKey('runs.run_uuid'), primary_key=True))
    timestamp: Optional[int] = Field(default=None, sa_column=Column('timestamp', BigInteger))

    runs: Optional['Runs'] = Relationship(back_populates='latest_metrics')


class LoggedModelMetrics(SQLModel, table=True):
    __tablename__ = 'logged_model_metrics'
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], name='fk_logged_model_metrics_experiment_id'),
        ForeignKeyConstraint(['model_id'], ['logged_models.model_id'], ondelete='CASCADE', name='fk_logged_model_metrics_model_id'),
        ForeignKeyConstraint(['run_id'], ['runs.run_uuid'], ondelete='CASCADE', name='fk_logged_model_metrics_run_id'),
        PrimaryKeyConstraint('model_id', 'metric_name', 'metric_timestamp_ms', 'metric_step', 'run_id', name='logged_model_metrics_pk'),
        Index('index_logged_model_metrics_model_id', 'model_id')
    )

    model_id: str = Field(sa_column=Column('model_id', String(36), primary_key=True))
    metric_name: str = Field(sa_column=Column('metric_name', String(500), primary_key=True))
    metric_timestamp_ms: int = Field(sa_column=Column('metric_timestamp_ms', BigInteger, primary_key=True))
    metric_step: int = Field(sa_column=Column('metric_step', BigInteger, primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, nullable=False))
    run_id: str = Field(sa_column=Column('run_id', String(32), primary_key=True))
    metric_value: Optional[float] = Field(default=None, sa_column=Column('metric_value', Float))
    dataset_uuid: Optional[str] = Field(default=None, sa_column=Column('dataset_uuid', String(36)))
    dataset_name: Optional[str] = Field(default=None, sa_column=Column('dataset_name', String(500)))
    dataset_digest: Optional[str] = Field(default=None, sa_column=Column('dataset_digest', String(36)))

    experiment: Optional['Experiments'] = Relationship(back_populates='logged_model_metrics')
    model: Optional['LoggedModels'] = Relationship(back_populates='logged_model_metrics')
    run: Optional['Runs'] = Relationship(back_populates='logged_model_metrics')


class LoggedModelParams(SQLModel, table=True):
    __tablename__ = 'logged_model_params'
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], name='fk_logged_model_params_experiment_id'),
        ForeignKeyConstraint(['model_id'], ['logged_models.model_id'], ondelete='CASCADE', name='fk_logged_model_params_model_id'),
        PrimaryKeyConstraint('model_id', 'param_key', name='logged_model_params_pk')
    )

    model_id: str = Field(sa_column=Column('model_id', String(36), primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, nullable=False))
    param_key: str = Field(sa_column=Column('param_key', String(255), primary_key=True))
    param_value: str = Field(sa_column=Column('param_value', Text, nullable=False))

    experiment: Optional['Experiments'] = Relationship(back_populates='logged_model_params')
    model: Optional['LoggedModels'] = Relationship(back_populates='logged_model_params')


class LoggedModelTags(SQLModel, table=True):
    __tablename__ = 'logged_model_tags'
    __table_args__ = (
        ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], name='fk_logged_model_tags_experiment_id'),
        ForeignKeyConstraint(['model_id'], ['logged_models.model_id'], ondelete='CASCADE', name='fk_logged_model_tags_model_id'),
        PrimaryKeyConstraint('model_id', 'tag_key', name='logged_model_tags_pk')
    )

    model_id: str = Field(sa_column=Column('model_id', String(36), primary_key=True))
    experiment_id: int = Field(sa_column=Column('experiment_id', Integer, nullable=False))
    tag_key: str = Field(sa_column=Column('tag_key', String(255), primary_key=True))
    tag_value: str = Field(sa_column=Column('tag_value', Text, nullable=False))

    experiment: Optional['Experiments'] = Relationship(back_populates='logged_model_tags')
    model: Optional['LoggedModels'] = Relationship(back_populates='logged_model_tags')


class Metrics(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('key', 'timestamp', 'step', 'run_uuid', 'value', 'is_nan', name='metric_pk'),
        Index('index_metrics_run_uuid', 'run_uuid')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    value: float = Field(sa_column=Column('value', Float, primary_key=True))
    timestamp: int = Field(sa_column=Column('timestamp', BigInteger, primary_key=True))
    run_uuid: str = Field(sa_column=Column('run_uuid', ForeignKey('runs.run_uuid'), primary_key=True))
    step: int = Field(sa_column=Column('step', BigInteger, primary_key=True, server_default=text("'0'")))
    is_nan: bool = Field(sa_column=Column('is_nan', Boolean, primary_key=True, server_default=text("'0'")))

    runs: Optional['Runs'] = Relationship(back_populates='metrics')


class ModelVersionTags(SQLModel, table=True):
    __tablename__ = 'model_version_tags'
    __table_args__ = (
        ForeignKeyConstraint(['name', 'version'], ['model_versions.name', 'model_versions.version'], onupdate='CASCADE'),
        PrimaryKeyConstraint('key', 'name', 'version', name='model_version_tag_pk')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    name: str = Field(sa_column=Column('name', String(256), primary_key=True))
    version: int = Field(sa_column=Column('version', Integer, primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(5000)))

    model_versions: Optional['ModelVersions'] = Relationship(back_populates='model_version_tags')


class Params(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('key', 'run_uuid', name='param_pk'),
        Index('index_params_run_uuid', 'run_uuid')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    value: str = Field(sa_column=Column('value', String(8000), nullable=False))
    run_uuid: str = Field(sa_column=Column('run_uuid', ForeignKey('runs.run_uuid'), primary_key=True))

    runs: Optional['Runs'] = Relationship(back_populates='params')


class Tags(SQLModel, table=True):
    __table_args__ = (
        PrimaryKeyConstraint('key', 'run_uuid', name='tag_pk'),
        Index('index_tags_run_uuid', 'run_uuid')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    run_uuid: str = Field(sa_column=Column('run_uuid', ForeignKey('runs.run_uuid'), primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(8000)))

    runs: Optional['Runs'] = Relationship(back_populates='tags')


class TraceRequestMetadata(SQLModel, table=True):
    __tablename__ = 'trace_request_metadata'
    __table_args__ = (
        ForeignKeyConstraint(['request_id'], ['trace_info.request_id'], ondelete='CASCADE', name='fk_trace_request_metadata_request_id'),
        PrimaryKeyConstraint('key', 'request_id', name='trace_request_metadata_pk'),
        Index('index_trace_request_metadata_request_id', 'request_id')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    request_id: str = Field(sa_column=Column('request_id', String(50), primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(8000)))

    request: Optional['TraceInfo'] = Relationship(back_populates='trace_request_metadata')


class TraceTags(SQLModel, table=True):
    __tablename__ = 'trace_tags'
    __table_args__ = (
        ForeignKeyConstraint(['request_id'], ['trace_info.request_id'], ondelete='CASCADE', name='fk_trace_tags_request_id'),
        PrimaryKeyConstraint('key', 'request_id', name='trace_tag_pk'),
        Index('index_trace_tags_request_id', 'request_id')
    )

    key: str = Field(sa_column=Column('key', String(250), primary_key=True))
    request_id: str = Field(sa_column=Column('request_id', String(50), primary_key=True))
    value: Optional[str] = Field(default=None, sa_column=Column('value', String(8000)))

    request: Optional['TraceInfo'] = Relationship(back_populates='trace_tags')
