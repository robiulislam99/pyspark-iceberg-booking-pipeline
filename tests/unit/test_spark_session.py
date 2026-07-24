"""
Unit tests for src/clients/spark_session.py

Run:
    docker compose exec spark pytest tests/unit/test_spark_session.py -v
"""

from unittest.mock import MagicMock, patch

import clients.spark_session as spark_session


def _mock_builder():
    """Build a MagicMock that mimics SparkSession.builder's fluent chain."""
    builder = MagicMock()
    builder.appName.return_value = builder
    builder.config.return_value = builder
    builder.master.return_value = builder
    return builder


def test_get_spark_configures_iceberg_and_sedona_packages():
    builder = _mock_builder()
    mock_session = MagicMock()
    builder.getOrCreate.return_value = mock_session

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext") as MockSedonaContext:
        MockSparkSession.builder = builder
        MockSedonaContext.create.return_value = mock_session

        result = spark_session.get_spark(app_name="test-app")

        builder.appName.assert_called_once_with("test-app")

        jars_call = [call for call in builder.config.call_args_list if call.args[0] == "spark.jars.packages"]
        assert len(jars_call) == 1
        packages = jars_call[0].args[1]
        assert spark_session.ICEBERG_PACKAGE in packages
        assert spark_session.SEDONA_PACKAGE in packages

        MockSedonaContext.create.assert_called_once_with(mock_session)
        assert result is mock_session


def test_get_spark_sets_sql_extensions():
    builder = _mock_builder()

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext"):
        MockSparkSession.builder = builder

        spark_session.get_spark()

        extensions_call = [call for call in builder.config.call_args_list if call.args[0] == "spark.sql.extensions"]
        assert len(extensions_call) == 1
        extensions_value = extensions_call[0].args[1]
        assert "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions" in extensions_value
        assert "org.apache.sedona.sql.SedonaSqlExtensions" in extensions_value


def test_get_spark_sets_local_iceberg_catalog():
    builder = _mock_builder()

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext"):
        MockSparkSession.builder = builder

        spark_session.get_spark()

        config_calls = {call.args[0]: call.args[1] for call in builder.config.call_args_list}
        assert config_calls["spark.sql.catalog.local"] == "org.apache.iceberg.spark.SparkCatalog"
        assert config_calls["spark.sql.catalog.local.type"] == "hadoop"
        assert config_calls["spark.sql.catalog.local.warehouse"] == spark_session.WAREHOUSE_PATH


def test_get_spark_sets_kryo_serializer_for_sedona():
    builder = _mock_builder()

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext"):
        MockSparkSession.builder = builder

        spark_session.get_spark()

        config_calls = {call.args[0]: call.args[1] for call in builder.config.call_args_list}
        assert config_calls["spark.serializer"] == "org.apache.spark.serializer.KryoSerializer"
        assert config_calls["spark.kryo.registrator"] == "org.apache.sedona.core.serde.SedonaKryoRegistrator"


def test_get_spark_uses_local_master():
    builder = _mock_builder()

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext"):
        MockSparkSession.builder = builder

        spark_session.get_spark()

        builder.master.assert_called_once_with("local[*]")


def test_get_spark_default_app_name():
    builder = _mock_builder()

    with patch("clients.spark_session.SparkSession") as MockSparkSession, patch("clients.spark_session.SedonaContext"):
        MockSparkSession.builder = builder

        spark_session.get_spark()

        builder.appName.assert_called_once_with("booking-etl")
