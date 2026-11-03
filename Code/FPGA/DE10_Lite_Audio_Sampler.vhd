library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity DE10_Lite_Audio_Sampler is
    port (
        -- Clocks
        ADC_CLK_10    : in  std_logic; -- PIN_N5 (10 MHz สำหรับ ADC PLL)
        MAX10_CLK1_50 : in  std_logic; -- PIN_P11 (50 MHz System Clock)
        
        -- Push Button Reset (KEY0 / PIN_B8, Active Low)
        KEY           : in  std_logic_vector(0 downto 0);
        
        -- Timing Probe output to GPIO JP1 Pin 1 (PIN_V10)
        TIMING_PROBE  : out std_logic;
        
        -- SPI Slave Interface to ESP32 (Header JP1)
        SPI_SCK       : in  std_logic; -- JP1 Pin 2 (PIN_W10)
        SPI_CS        : in  std_logic; -- JP1 Pin 3 (PIN_V9)
        SPI_MOSI      : in  std_logic; -- JP1 Pin 4 (PIN_W9)
        SPI_MISO      : out std_logic  -- JP1 Pin 5 (PIN_V8)
    );
end entity DE10_Lite_Audio_Sampler;

architecture Structural of DE10_Lite_Audio_Sampler is

    -- Component จาก Platform Designer (Qsys) ชื่อ adc_qsys
    component adc_qsys is
        port (
            clk_clk                              : in  std_logic := '0';
            reset_reset_n                        : in  std_logic := '0';
            adc_pll_clk_clk                      : in  std_logic := '0';
            modular_adc_0_command_valid          : in  std_logic := '0';
            modular_adc_0_command_channel        : in  std_logic_vector(4 downto 0) := (others => '0');
            modular_adc_0_command_startofpacket  : in  std_logic := '0';
            modular_adc_0_command_endofpacket    : in  std_logic := '0';
            modular_adc_0_command_ready          : out std_logic;
            modular_adc_0_response_valid         : out std_logic;
            modular_adc_0_response_channel       : out std_logic_vector(4 downto 0);
            modular_adc_0_response_data          : out std_logic_vector(11 downto 0);
            modular_adc_0_response_startofpacket : out std_logic;
            modular_adc_0_response_endofpacket   : out std_logic
        );
    end component adc_qsys;

    -- Signals สำหรับเชื่อม ADC IP
    signal cmd_valid   : std_logic;
    signal cmd_channel : std_logic_vector(4 downto 0);
    signal cmd_sop     : std_logic;
    signal cmd_eop     : std_logic;
    signal cmd_ready   : std_logic;
    signal rsp_valid   : std_logic;
    signal rsp_channel : std_logic_vector(4 downto 0);
    signal rsp_data    : std_logic_vector(11 downto 0);
    signal rsp_sop     : std_logic;
    signal rsp_eop     : std_logic;

    -- Internal Interconnect Signals
    signal sample_tick_sig : std_logic;
    signal audio_sample    : std_logic_vector(15 downto 0);
    signal wr_addr_cnt     : unsigned(9 downto 0) := (others => '0');
    signal bram_rd_addr    : std_logic_vector(9 downto 0);
    signal bram_rd_data    : std_logic_vector(15 downto 0);
    
    -- Ping-Pong Bank Control
    signal wr_bank         : std_logic := '0';
    signal rd_bank         : std_logic := '1';
    signal cs_sync         : std_logic_vector(1 downto 0) := "11";

begin

    -- 1. ระบบ Qsys ที่รวม ALTPLL และ Modular ADC เข้าด้วยกัน
    u_adc_qsys: adc_qsys
        port map (
            clk_clk                              => MAX10_CLK1_50,
            reset_reset_n                        => KEY(0),
            adc_pll_clk_clk                      => ADC_CLK_10,
            modular_adc_0_command_valid          => cmd_valid,
            modular_adc_0_command_channel        => cmd_channel,
            modular_adc_0_command_startofpacket  => cmd_sop,
            modular_adc_0_command_endofpacket    => cmd_eop,
            modular_adc_0_command_ready          => cmd_ready,
            modular_adc_0_response_valid         => rsp_valid,
            modular_adc_0_response_channel       => rsp_channel,
            modular_adc_0_response_data          => rsp_data,
            modular_adc_0_response_startofpacket => rsp_sop,
            modular_adc_0_response_endofpacket   => rsp_eop
        );

    -- 2. Hardware Sampling Clock Generator (16 kHz)
    u_clk_gen: entity work.clk_en_gen
        generic map (
            CLK_FREQ_HZ    => 50000000,
            SAMPLE_RATE_HZ => 16000
        )
        port map (
            clk_50m     => MAX10_CLK1_50,
            rst_n       => KEY(0),
            sample_tick => sample_tick_sig,
            probe_out   => TIMING_PROBE
        );

    -- 3. โมดูลอ่านค่า ADC ทุกจังหวะ 16 kHz
    u_adc_reader: entity work.adc_mic_reader
        port map (
            clk_50m          => MAX10_CLK1_50,
            rst_n            => KEY(0),
            sample_tick      => sample_tick_sig,
            cmd_valid        => cmd_valid,
            cmd_channel      => cmd_channel,
            cmd_sop          => cmd_sop,
            cmd_eop          => cmd_eop,
            cmd_ready        => cmd_ready,
            rsp_valid        => rsp_valid,
            rsp_channel      => rsp_channel,
            rsp_data         => rsp_data,
            rsp_sop          => rsp_sop,
            rsp_eop          => rsp_eop,
            audio_sample_out => audio_sample
        );

    -- 4. Write Address Counter & Ping-Pong Bank Switcher
    process(MAX10_CLK1_50, KEY(0))
    begin
        if KEY(0) = '0' then
            wr_addr_cnt <= (others => '0');
            wr_bank     <= '0';
            rd_bank     <= '1';
            cs_sync     <= "11";
        elsif rising_edge(MAX10_CLK1_50) then
            cs_sync <= cs_sync(0) & SPI_CS;

            -- เมื่อ CS เป็น HIGH (Idle) ให้ชี้ rd_bank ไปยัง Bank ที่เขียนเสร็จแล้วเสมอ
            if cs_sync(1) = '1' then
                rd_bank <= not wr_bank;
            end if;

            -- นับตำแหน่งเขียนทุกๆ 16 kHz เมื่อครบ 1024 ตัวอย่างให้สลับ Bank
            if sample_tick_sig = '1' then
                if wr_addr_cnt = 1023 then
                    wr_addr_cnt <= (others => '0');
                    wr_bank     <= not wr_bank;
                else
                    wr_addr_cnt <= wr_addr_cnt + 1;
                end if;
            end if;
        end if;
    end process;

    -- 5. Dual-Port Ping-Pong Block RAM
    u_bram: entity work.bram_dp_1024x16
        port map (
            clk     => MAX10_CLK1_50,
            we      => sample_tick_sig,
            bank_w  => wr_bank,
            addr_w  => std_logic_vector(wr_addr_cnt),
            data_w  => audio_sample,
            bank_r  => rd_bank,
            addr_r  => bram_rd_addr,
            data_r  => bram_rd_data
        );

    -- 6. SPI Slave Interface to ESP32
    u_spi_slave: entity work.spi_slave
        port map (
            clk_50m  => MAX10_CLK1_50,
            rst_n    => KEY(0),
            spi_sck  => SPI_SCK,
            spi_cs   => SPI_CS,
            spi_mosi => SPI_MOSI,
            spi_miso => SPI_MISO,
            rd_addr  => bram_rd_addr,
            rd_data  => bram_rd_data
        );

end architecture Structural;